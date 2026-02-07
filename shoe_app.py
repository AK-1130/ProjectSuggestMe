import streamlit as st
import pandas as pd
import sqlite3
import re

# --- CONFIGURATION ---
st.set_page_config(page_title="Shoe Selection Pro", layout="wide")
DB_FILE = "shoes_drive.db"

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # stored_url is the converted "viewable" link
    c.execute('''CREATE TABLE IF NOT EXISTS shoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  original_link TEXT, 
                  stored_url TEXT)''')
    
    # Votes table
    c.execute('''CREATE TABLE IF NOT EXISTS votes 
                 (user_email TEXT, 
                  shoe_id INTEGER, 
                  upvoted INTEGER DEFAULT 0, 
                  is_favorite INTEGER DEFAULT 0, 
                  PRIMARY KEY (user_email, shoe_id))''')
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

# --- GOOGLE DRIVE LINK CONVERTER ---
def convert_drive_link(url):
    """
    Extracts the ID from a Google Drive share link and creates a direct image URL.
    Works for standard 'drive.google.com/file/d/ID/view' links.
    """
    # Regex to find the ID between '/d/' and '/view' or other endings
    file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if file_id_match:
        file_id = file_id_match.group(1)
        # Using lh3.googleusercontent.com is often more reliable for embedding than drive.google.com/uc
        return f"https://lh3.googleusercontent.com/d/{file_id}"
    return None

# --- AUTHENTICATION ---
def check_admin(username, password):
    # Hardcoded credentials as requested
    return username == "AK1130" and password == "3110"

def logout():
    st.session_state.clear()
    st.rerun()

# --- VOTING LOGIC ---
@st.dialog("Change Favorite Shoe?")
def confirm_switch_favorite(user_email, new_shoe_id, old_shoe_id):
    st.write(f"You already have a favorite (Shoe #{old_shoe_id}).")
    st.write("Do you want to switch your favorite to this one?")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Switch"):
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, old_shoe_id))
            c.execute("""INSERT INTO votes (user_email, shoe_id, is_favorite) VALUES (?, ?, 1)
                         ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", 
                      (user_email, new_shoe_id))
            conn.commit()
            conn.close()
            st.rerun()
    with col2:
        if st.button("No, Keep Old"):
            st.rerun()

def toggle_upvote(user_email, shoe_id, current_status):
    new_status = 0 if current_status == 1 else 1
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO votes (user_email, shoe_id, upvoted) VALUES (?, ?, ?)
                 ON CONFLICT(user_email, shoe_id) DO UPDATE SET upvoted = ?""",
              (user_email, shoe_id, new_status, new_status))
    conn.commit()
    conn.close()
    st.rerun()

def handle_favorite_click(user_email, shoe_id, current_fav_id):
    conn = get_db()
    c = conn.cursor()
    
    if current_fav_id == shoe_id:
        c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    elif current_fav_id is None:
        c.execute("""INSERT INTO votes (user_email, shoe_id, is_favorite) VALUES (?, ?, 1)
                     ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", 
                  (user_email, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    else:
        conn.close()
        confirm_switch_favorite(user_email, shoe_id, current_fav_id)

# --- ADMIN PAGE ---
def admin_dashboard():
    st.title("Admin Dashboard 🛠️")
    
    with st.expander("ℹ️ How to add photos from Google Drive", expanded=True):
        st.write("""
        1. Go to your Google Drive folder.
        2. Select your photos (Right click -> Share -> Copy Link).
        3. **IMPORTANT:** Ensure access is set to **'Anyone with the link'**.
        4. Paste the links below (one per line).
        """)

    # Text Area for Bulk Links
    links_input = st.text_area("Paste Google Drive Links Here (One per line)")
    
    if st.button("Process & Add Links"):
        if links_input.strip():
            raw_links = links_input.split('\n')
            conn = get_db()
            c = conn.cursor()
            added_count = 0
            
            for link in raw_links:
                link = link.strip()
                if link:
                    direct_url = convert_drive_link(link)
                    if direct_url:
                        c.execute("INSERT INTO shoes (original_link, stored_url) VALUES (?, ?)", 
                                  (link, direct_url))
                        added_count += 1
            
            conn.commit()
            conn.close()
            
            if added_count > 0:
                st.success(f"Successfully added {added_count} photos!")
                st.rerun()
            else:
                st.error("Could not recognize any valid Google Drive links. Make sure they are standard sharing links.")
        else:
            st.warning("Please paste some links first.")

    st.divider()
    
    # Hall of Fame
    st.subheader("🏆 Hall of Fame (Top 5)")
    conn = get_db()
    query = """
    SELECT s.id, s.stored_url, 
           COALESCE(SUM(v.upvoted), 0) as up_count, 
           COALESCE(SUM(v.is_favorite), 0) as fav_count
    FROM shoes s
    LEFT JOIN votes v ON s.id = v.shoe_id
    GROUP BY s.id
    ORDER BY fav_count DESC, up_count DESC
    LIMIT 5
    """
    top_5 = pd.read_sql(query, conn)
    conn.close()
    
    if not top_5.empty:
        for idx, row in top_5.iterrows():
            c1, c2 = st.columns([1, 4])
            with c1:
                st.image(row['stored_url'])
            with c2:
                st.markdown(f"### #{idx+1} (Shoe {row['id']})")
                st.markdown(f"❤️ **Favorites:** {row['fav_count']} | 👍 **Upvotes:** {row['up_count']}")
            st.divider()
    else:
        st.info("No votes yet.")

# --- FOLKS GALLERY PAGE ---
def folks_gallery():
    user = st.session_state['user_id']
    st.title("👟 Shoe Voting Gallery")
    
    with st.expander("🆕 First time? Click for Guide"):
        st.info("👍 = Like (Upvote) | ❤️ = The One (Favorite)")

    conn = get_db()
    
    # User's votes
    my_votes = pd.read_sql("SELECT * FROM votes WHERE user_email = ?", conn, params=(user,))
    my_upvotes = my_votes[my_votes['upvoted'] == 1]['shoe_id'].tolist()
    
    fav_row = my_votes[my_votes['is_favorite'] == 1]
    my_fav_id = fav_row.iloc[0]['shoe_id'] if not fav_row.empty else None

    # Fetch Sorted Shoes
    query = """
    SELECT s.id, s.stored_url, 
           COALESCE(SUM(v.is_favorite), 0) as total_favs,
           COALESCE(SUM(v.upvoted), 0) as total_ups
    FROM shoes s
    LEFT JOIN votes v ON s.id = v.shoe_id
    GROUP BY s.id
    ORDER BY total_favs DESC, total_ups DESC, s.id ASC
    """
    shoes_data = pd.read_sql(query, conn)
    conn.close()

    if shoes_data.empty:
        st.warning("Waiting for Admin to add Google Drive links...")
        return

    cols = st.columns(3)
    for idx, row in shoes_data.iterrows():
        shoe_id = row['id']
        url = row['stored_url']
        
        is_upvoted = shoe_id in my_upvotes
        is_fav = (shoe_id == my_fav_id)
        
        with cols[idx % 3]:
            st.container(border=True)
            # Display Image from Drive URL
            st.image(url, use_container_width=True)
            st.caption(f"Shoe #{shoe_id}")
            
            b1, b2 = st.columns(2)
            if b1.button(f"{'👍 Liked' if is_upvoted else '👍 Like'}", 
                         key=f"up_{shoe_id}", 
                         type="primary" if is_upvoted else "secondary", 
                         use_container_width=True):
                toggle_upvote(user, shoe_id, 1 if is_upvoted else 0)
                
            if b2.button(f"{'❤️ Fav' if is_fav else '🤍 Fav'}", 
                         key=f"fav_{shoe_id}", 
                         type="primary" if is_fav else "secondary", 
                         use_container_width=True):
                handle_favorite_click(user, shoe_id, my_fav_id)

# --- LOGIN PAGE ---
def login():
    st.markdown("<h1 style='text-align: center;'>👟 The Shoe Poll</h1>", unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.container(border=True):
            tabs = st.tabs(["Folks (Vote)", "Admin (Login)"])
            with tabs[0]:
                name = st.text_input("Name")
                email = st.text_input("Google Email")
                if st.button("Enter Gallery", type="primary"):
                    if name and email:
                        st.session_state['user_role'] = 'folk'
                        st.session_state['user_id'] = email
                        st.session_state['user_name'] = name
                        st.rerun()
            with tabs[1]:
                aid = st.text_input("Admin ID")
                apass = st.text_input("Password", type="password")
                if st.button("Admin Login"):
                    if check_admin(aid, apass):
                        st.session_state['user_role'] = 'admin'
                        st.session_state['user_id'] = 'ADMIN'
                        st.rerun()
                    else:
                        st.error("Wrong Password")

# --- MAIN ---
def main():
    init_db()
    if 'user_role' not in st.session_state:
        login()
    else:
        with st.sidebar:
            st.write(f"User: **{st.session_state.get('user_name', 'Admin')}**")
            if st.button("Logout"):
                logout()
        
        if st.session_state['user_role'] == 'admin':
            admin_dashboard()
        else:
            folks_gallery()

if __name__ == "__main__":
    main()