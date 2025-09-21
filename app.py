# app.py
"""
Roamio AI Trip Planner (Python 3.13 + Gemini 1.5 Flash)
Features:
- Home page with logo & background
- Plan a trip page
- Itinerary with Google Maps images & clickable links
"""

import os
import json
import time
from typing import Optional
import streamlit as st
import requests
import google.generativeai as genai
import re  # <-- Added for location extraction

# ----------------- CONFIG -----------------
GOOGLE_API_KEY = "AIzaSyAU0P4W-8F8ZkCbS8f-ilCccrOiVvvi3fM" #os.getenv("GOOGLE_API_KEY")  # Gemini + Places
TRIPS_FILE = "saved_trips.json"

# ----------------- GEMINI SETUP -----------------
GEMINI_MODEL: Optional[genai.GenerativeModel] = None
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")

# ----------------- UTILS -----------------

def ensure_saved_trips_file() -> None:
    if not os.path.exists(TRIPS_FILE):
        with open(TRIPS_FILE, "w") as f:
            json.dump([], f)

def load_saved_trips() -> list[dict]:
    ensure_saved_trips_file()
    with open(TRIPS_FILE, "r") as f:
        return json.load(f)

def save_trip(trip: dict) -> None:
    trips = load_saved_trips()
    trips.append(trip)
    with open(TRIPS_FILE, "w") as f:
        json.dump(trips, f, indent=2)

def generate_itinerary_gemini(prompt: str) -> str:
    if not GEMINI_MODEL:
        return "ERROR: GOOGLE_API_KEY not set."
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Gemini error: {e}"

def fetch_places_google(destination: str, place_type: str="tourist_attraction", count: int=5) -> list[dict]:
    GOOGLE_MAPS_API_KEY = "AIzaSyASOtRR71J484CcXhvs3BBZByhIII8lNuU"
    if not GOOGLE_MAPS_API_KEY:
        return []
    query = f"top {place_type} in {destination}"
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_MAPS_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        results: list[dict] = []
        for item in data.get("results", [])[:count]:
            photo_url = None
            if "photos" in item and item["photos"]:
                ref = item["photos"][0].get("photo_reference")
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={ref}&key={GOOGLE_MAPS_API_KEY}"
            maps_url = f"https://www.google.com/maps/search/?api=1&query={item.get('name').replace(' ', '+')}&query_place_id={item.get('place_id','')}"
            results.append({
                "name": item.get("name"),
                "address": item.get("formatted_address"),
                "rating": item.get("rating"),
                "photo": photo_url,
                "maps_url": maps_url
            })
        return results
    except Exception as e:
        st.warning(f"Google Places error: {e}")
        return []

def build_itinerary_prompt(destination: str, days: int, budget: str, pax: str, interests: list[str]) -> str:
    interests_txt = ", ".join(interests) if interests else "general sightseeing"
    return (
        f"Create a {days}-day travel itinerary for {pax} traveling to {destination}. "
        f"Budget: {budget}. Interests: {interests_txt}. "
        "For each day: morning/afternoon/evening plan, costs, transport, and 3 restaurant" 
        "Suggest Stays With images with there location to google maps links. "
        "Suggest Restaurants With images with there location to google maps links."
        "Add a packing tip for local climate. Keep it concise and friendly."
    )

# ----------- NEW LOCATION EXTRACTION & DETAILS FUNCTIONS -----------

def extract_locations_from_itinerary(itinerary_text: str) -> list[str]:
    """
    Extracts suggested places and hotels from the itinerary text.
    Looks for lines starting with 'Visit', 'Stay at', 'Hotel', etc.
    """
    locations = set()
    for line in itinerary_text.split('\n'):
        match = re.search(r"(Visit|Stay at|Hotel|Restaurant|Explore|Check-in at)\s+([A-Za-z0-9 ,'-]+)", line)
        if match:
            loc = match.group(2).strip()
            if len(loc) > 2:
                locations.add(loc)
    return list(locations)

def fetch_place_details(name: str, destination: str) -> Optional[dict]:
    """
    Fetches place details from Google Places API by name and destination.
    """
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    query = f"{name} in {destination}"
    params = {"query": query, "key": GOOGLE_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("results"):
            item = data["results"][0]
            photo_url = None
            if "photos" in item and item["photos"]:
                ref = item["photos"][0].get("photo_reference")
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={ref}&key={GOOGLE_API_KEY}"
            maps_url = f"https://www.google.com/maps/search/?api=1&query={item.get('name').replace(' ', '+')}&query_place_id={item.get('place_id','')}"
            price_level = item.get("price_level")
            price_desc = {1: "Budget", 2: "Moderate", 3: "Expensive", 4: "Luxury"}.get(price_level, "")
            return {
                "name": item.get("name"),
                "address": item.get("formatted_address"),
                "rating": item.get("rating"),
                "photo": photo_url,
                "maps_url": maps_url,
                "description": item.get("types", []),
                "price": price_desc
            }
    except Exception as e:
        st.warning(f"Google Places error: {e}")
    return None

# ----------------- STREAMLIT APP -----------------
st.set_page_config(page_title="Roamio", layout="wide")

# ----------------- SIDEBAR NAV -----------------
st.sidebar.title("Roamio 🧭")
page = st.sidebar.radio("Navigate", ["Home", "Plan a Trip", "Saved Trips"])

# ----------------- HOME PAGE -----------------
if page == "Home":
    st.markdown(
        """
        <style>
        .bg {
            background-image: url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e');
            background-size: cover;
            background-position: center;
            height: 100vh;
        }
        .logo {
            width: 200px;
        }
        .centered {
            text-align: center;
            color: white;
            padding-top: 150px;
        }
        </style>
        <div class="bg">
            <div class="centered">
                <img src="https://raw.githubusercontent.com/yourusername/yourrepo/main/Assets/Logo.png" class="logo">
                <h1>Welcome to Roamio</h1>
                <p>Your AI-powered travel planner</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        '<div style="text-align:center; margin-top:-100px;"><a href="#Plan-a-Trip"><button style="padding:15px 30px; font-size:18px; border-radius:10px; background-color:#4CAF50; color:white; border:none;">Plan a Trip</button></a></div>',
        unsafe_allow_html=True
    )

# ----------------- PLAN A TRIP -----------------
elif page == "Plan a Trip":

    st.title("Plan Your Trip 🗺️")
    col1, col2 = st.columns([2,1])

    with col1:
        from_location = st.text_input("From", value="Hyderabad, India")
        dest = st.text_input("Destination", value="Jammu, India")
        days = st.number_input("Number of days", min_value=1, max_value=30, value=5)
        budget = st.selectbox("Budget", ["Economy", "Moderate", "Comfort", "Luxury"])
        pax = st.selectbox("Traveling as", ["Solo", "Couple", "Family", "Friends"])
        interests = st.multiselect("Interests", ["Sightseeing","Food","Culture","Hiking","Beaches","Shopping","Nightlife"], default=["Sightseeing","Food"])
        generate_btn = st.button("Generate Itinerary")

    with col2:
        st.header("Saved trips")
        trips = load_saved_trips()
        for i, t in enumerate(reversed(trips[-10:])):
            st.write(f"**{t['destination']}** — {t['days']} days — {t['pax']} — {t['budget']}")
            if st.button(f"Load #{i}", key=f"load_{i}"):
                st.session_state["loaded_trip"] = t


    if generate_btn:
        with st.spinner("Generating itinerary..."):
            prompt = build_itinerary_prompt(dest, days, budget, pax, interests)
            ai_text = generate_itinerary_gemini(prompt)
            st.session_state["latest_itinerary"] = {
                "from": from_location,
                "destination": dest,
                "days": days,
                "budget": budget,
                "pax": pax,
                "interests": interests,
                "generated_at": time.time(),
                "itinerary_text": ai_text
            }
            # Fetch top 6 places automatically
            st.session_state["places"] = fetch_places_google(dest, count=6)


    # Show itinerary if generated
    if "latest_itinerary" in st.session_state:
        it = st.session_state["latest_itinerary"]
        st.subheader(f"{it['from']} → {it['destination']} — {it['days']} Day Trip | {it['budget']} | {it['pax']} travelers")

        # Hotels / Top Places (Card style)
        if st.session_state.get("places"):
            st.markdown("### Top Places to Visit 📍")
            places = st.session_state["places"]
            for i in range(0, len(places), 3):
                cols = st.columns(3)
                for j, place in enumerate(places[i:i+3]):
                    with cols[j]:
                        if place.get("photo"):
                            # Clickable image opens Google Maps
                            st.markdown(
                                f'<a href="{place["maps_url"]}" target="_blank">'
                                f'<img src="{place["photo"]}" style="width:100%; border-radius:10px;">'
                                f'</a>',
                                unsafe_allow_html=True
                            )
                        st.markdown(f"**{place['name']}**")
                        if place.get("address"):
                            st.markdown(f"{place['address']}")
                        if place.get("rating"):
                            st.markdown(f"⭐ {place['rating']}")

        # ----------- NEW: Suggested Hotels & Places from Itinerary -----------
        st.markdown("### Suggested Hotels & Places 🏨")
        locations = extract_locations_from_itinerary(it["itinerary_text"])
        loc_details = []
        for loc in locations:
            details = fetch_place_details(loc, it["destination"])
            if details:
                loc_details.append(details)
        if loc_details:
            for i in range(0, len(loc_details), 3):
                cols = st.columns(3)
                for j, loc in enumerate(loc_details[i:i+3]):
                    with cols[j]:
                        if loc.get("photo"):
                            st.markdown(
                                f'<a href="{loc["maps_url"]}" target="_blank">'
                                f'<img src="{loc["photo"]}" style="width:100%; border-radius:10px;">'
                                f'</a>',
                                unsafe_allow_html=True
                            )
                        st.markdown(f"**{loc['name']}**")
                        if loc.get("address"):
                            st.markdown(f"{loc['address']}")
                        if loc.get("rating"):
                            st.markdown(f"⭐ {loc['rating']}")
                        if loc.get("price"):
                            st.markdown(f"💲 {loc['price']}")
                        if loc.get("description"):
                            st.markdown(f"_{', '.join(loc['description'])}_")

        # AI itinerary text below with day-wise separation
        st.markdown("### Trip Itinerary 📝")
        st.markdown(it["itinerary_text"])

        # Save Itinerary Button
        if st.button("Save Itinerary", key="save_itinerary"):
            save_trip(it)
            st.success("Trip saved!")
            # Force update of saved trips in session state
            st.session_state["saved_trips"] = load_saved_trips()

# ----------------- SAVED TRIPS -----------------
elif page == "Saved Trips":

    st.title("Saved Trips 💾")
    # Use session state for instant update after saving
    trips = st.session_state.get("saved_trips", load_saved_trips())
    if trips:
        for t in reversed(trips):
            # Better trip name: From, To, Days, Interests
            trip_name = f"{t.get('from', 'Unknown')} → {t.get('destination', 'Unknown')} | {t.get('days', '')} days | {', '.join(t.get('interests', []))}".replace('Unknown → Unknown |  days | ', 'Unnamed Trip')
            with st.expander(trip_name):
                st.markdown(f"**From:** {t.get('from', '')}")
                st.markdown(f"**To:** {t.get('destination', '')}")
                st.markdown(f"**Days:** {t.get('days', '')}")
                st.markdown(f"**Traveling as:** {t.get('pax', '')}")
                st.markdown(f"**Budget:** {t.get('budget', '')}")
                interests = ', '.join(t.get('interests', []))
                st.markdown(f"**Interests:** {interests}")
                st.markdown("---")
                st.markdown(t.get("itinerary_text", ""))
    else:
        st.info("No saved trips yet.")

st.caption("Made with ❤️ using Gemini 1.5 Flash & Google Places — Roamio 2025")