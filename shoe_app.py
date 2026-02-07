import streamlit as st
import pandas as pd
import sqlite3
import os

# --- CONFIGURATION ---
st.set_page_config(page_title="Shoe Selection Pro", layout="wide")
DB_FILE = "shoes_v3.db"
IMAGE_FOLDER = "images"

# Ensure local image directory exists
if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS shoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  filename TEXT)''')
    
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

# --- ADMIN ACTIONS ---
def save_uploaded_files(uploaded_files):
    conn = get_db()
    c = conn.cursor()
    count = 0
    for uploaded_file in uploaded_files:
        # Save file to disk
        file_path = os.path.join(IMAGE_FOLDER, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        # Add to DB
        c.execute("INSERT INTO shoes (filename) VALUES (?)", (uploaded_file.name,))
        count += 1
    conn.commit()
    conn.close()
    return count

def delete_shoe(shoe_id, filename):
    conn = get_db()
    c = conn.cursor()
    
    # 1. Delete from DB
    c.execute("DELETE FROM shoes WHERE id = ?", (shoe_id,))
    c.execute("DELETE FROM votes WHERE shoe_id = ?", (shoe_id,))
    conn.commit()
    conn.close()
    
    # 2. Delete file from disk (try/except in case file is missing)
    try:
        file_path = os.path.join(IMAGE_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        st.error(f"Error deleting file: {e}")

# --- VOTING LOGIC ---
@st.dialog("Change Favorite Shoe?")
def confirm_switch_favorite(user_email, new_shoe_id, old_shoe_id):
    st.write(f"You have a favorite (Shoe #{old_shoe_id}). Switch to this one?")
    col1, col2 = st.columns(2)
    if col1.button("Yes, Switch"):
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, old_shoe_id))
        c.execute("""INSERT INTO votes (user_email, shoe_id, is_favorite) VALUES (?, ?, 1)
                     ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", (user_email, new_shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    if col2.button("No"):
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
    if current_fav_id == shoe_id: # Un-favorite
        c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    elif current_fav_id is None: # New favorite
        c.execute("""INSERT INTO votes (user_email, shoe_id, is_favorite) VALUES (?, ?, 1)
                     ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", (user_email, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    else: # Switch favorite
        conn.close()
        confirm_switch_favorite(user_email, shoe_id, current_fav_id)

# --- ADMIN PAGE ---
def admin_dashboard():
    st.title("Admin Dashboard 🛠️")
    
    tabs = st.tabs(["📤 Upload Photos", "🗑️ Manage Images", "📊 Stats"])
    
    # TAB 1: UPLOAD
    with tabs[0]:
        st.subheader("Bulk Upload")
        st.info("Drag and drop multiple files here. They will be saved immediately.")
        uploaded_files = st.file_uploader("Choose photos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'])
        
        if uploaded_files:
            if st.button(f"Save {len(uploaded_files)} Photos"):
                count = save_uploaded_files(uploaded_files)
                st.success(f"Saved {count} images!")
                st.rerun()

    # TAB 2: MANAGE / DELETE
    with tabs[1]:
        st.subheader("Manage Gallery")
        conn = get_db()
        all_shoes = pd.read_sql("SELECT * FROM shoes", conn)
        conn.close()
        
        if all_shoes.empty:
            st.warning("No images found.")
        else:
            # Display in grid for deletion
            cols = st.columns(4)
            for idx, row in all_shoes.iterrows():
                with cols[idx % 4]:
                    st.container(border=True)
                    img_path = os.path.join(IMAGE_FOLDER, row['filename'])
                    
                    # specific check if file exists to avoid error on missing files
                    if os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                    else:
                        st.error("File missing")
                        
                    st.caption(f"ID: {row['id']}")
                    if st.button("🗑️ Delete", key=f"del_{row['id']}", type="primary"):
                        delete_shoe(row['id'], row['filename'])
                        st.rerun()

    # TAB 3: STATS
    with tabs[2]:
        st.subheader("Live Results")
        conn = get_db()
        # Join tables
        query = """
        SELECT s.id, s.filename, 
            COALESCE(SUM(v.upvoted), 0) as ups, 
            COALESCE(SUM(v.is_favorite), 0) as favs
        FROM shoes s
        LEFT JOIN votes v ON s.id = v.shoe_id
        GROUP BY s.id
        ORDER BY favs
