import streamlit as st
import pandas as pd
import sqlite3
import os
import shutil

# --- CONFIGURATION ---
st.set_page_config(page_title="Shoe Selection Pro", layout="wide")
DB_FILE = "shoes_v4.db"
IMAGE_FOLDER = "images"
ITEMS_PER_PAGE = 10

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
    c.execute("DELETE FROM shoes WHERE id = ?", (shoe_id,))
    c.execute("DELETE FROM votes WHERE shoe_id = ?", (shoe_id,))
    conn.commit()
    conn.close()
    
    try:
        file_path = os.path.join(IMAGE_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        st.error(f"Error deleting file: {e}")

def delete_all_shoes():
    conn = get_db()
    c = conn.cursor()
    # Clear Tables
    c.execute("DELETE FROM shoes")
    c.execute("DELETE FROM votes")
    # Reset ID counters
    c.execute("DELETE FROM sqlite_sequence WHERE name='shoes'")
    conn.commit()
    conn.close()
    
    # Clear Folder
    for filename in os.listdir(IMAGE_FOLDER):
        file_path = os.path.join(IMAGE_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            st.error(f"Failed to delete {file_path}. Reason: {e}")

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
        
        # Delete All Section
        with st.expander("⚠️ Danger Zone: Delete All"):
            st.warning("This will delete ALL images and ALL votes forever.")
            if st.button("🗑️ DELETE EVERYTHING", type="primary"):
                delete_all_shoes()
                st.success("All data wiped.")
                st.rerun()
        
        st.divider()

        conn = get_db()
        all_shoes = pd.read_sql("SELECT * FROM shoes", conn)
        conn.close()
        
        if all_shoes.empty:
            st.warning("No images found.")
        else:
            # --- PAGINATION LOGIC ---
            if "page_number" not in st.session_state:
                st.session_state.page_number = 0

            total_pages = max(1, (len(all_shoes) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            
            # Ensure page number is valid
            if st.session_state.page_number >= total_pages:
                st.session_state.page_number = total_pages - 1

            # Slice the dataframe for current page
            start_idx = st.session_state.page_number * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            current_batch = all_shoes.iloc[start_idx:end_idx]

            # Display Batch
            st.write(f"Showing page {st.session_state.page_number + 1} of {total_pages}")
            
            cols = st.columns(4)
            for idx, row in current_batch.iterrows():
                with cols[idx % 4]:
                    st.container(border=True)
                    img_path = os.path.join(IMAGE_FOLDER, row['filename'])
                    
                    if os.path.exists(img_path):
                        st.image(img_path, use_container_width=True)
                    else:
                        st.error("File missing")
                        
                    st.caption(f"ID: {row['id']}")
                    if st.button("🗑️ Delete", key=f"del_{row['id']}", type="secondary"):
                        delete_shoe(row['id'], row['filename'])
                        st.rerun()

            # Pagination Controls
            st.divider()
            c_prev, c_mid, c_next = st.columns([1, 2, 1])
            
            if c_prev.button("⬅️ Previous") and st.session_state.page_number > 0:
                st.session_state.page_number -= 1
                st.rerun()
            
            if c_next.button("Next ➡️") and st.session_state.page_number < total_pages - 1:
                st.session_state.page_number += 1
                st.rerun()

    # TAB 3: STATS
    with tabs[2]:
        st.subheader("Live Results")
        conn = get_db()
        query = """
        SELECT s.id, s.filename, 
            COALESCE(SUM(v.upvoted), 0) as ups, 
            COALESCE(SUM(v.is_favorite), 0) as favs
        FROM shoes s
        LEFT JOIN votes v ON s.id = v.shoe_id
        GROUP BY s.id
        ORDER BY favs DESC, ups DESC
        LIMIT 10
        """
        stats = pd.read_sql(query, conn)
        conn.close()
        
        if not stats.empty:
            st.dataframe(stats)
            st.bar_chart(stats.set_index('id')['ups'])
        else:
            st.info("No data yet.")

# --- FOLKS PAGE ---
def folks_gallery():
    user = st.session_state['user_id']
    st.title("👟 Shoe Voting Gallery")
    
    with st.expander("ℹ️ Click for Help"):
        st.markdown("Use **👍 (Like)** for good shoes and **❤️ (Favorite)** for the BEST one.")

    conn = get_db()
    
    # Get User Status
    my_votes = pd.read_sql("SELECT * FROM votes WHERE user_email = ?", conn, params=(user,))
    my_ups = my_votes[my_votes['upvoted'] == 1]['shoe_id'].tolist()
    fav_row = my_votes[my_votes['is_favorite'] == 1]
    my_fav_id = fav_row.iloc[0]['shoe_id'] if not fav_row.empty else None

    # Get Shoes Sorted
    query = """
    SELECT s.id, s.filename, 
           COALESCE(SUM(v.is_favorite), 0) as total_favs,
           COALESCE(SUM(v.upvoted), 0) as total_ups
    FROM shoes s
    LEFT JOIN votes v ON s.id = v.shoe_id
    GROUP BY s.id
    ORDER BY total_favs DESC, total_ups DESC, s.id ASC
    """
    shoes = pd.read_sql(query, conn)
    conn.close()

    if shoes.empty:
        st.warning("Gallery is empty.")
        return

    cols = st.columns(3)
    for idx, row in shoes.iterrows():
        sid = row['id']
        fname = row['filename']
        img_path = os.path.join(IMAGE_FOLDER, fname)
        
        # Calculate State
        is_up = sid in my_ups
        is_fav = (sid == my_fav_id)
        
        with cols[idx % 3]:
            st.container(border=True)
            if os.path.exists(img_path):
                st.image(img_path, use_container_width=True)
            else:
                st.error("Image not found")
            
            st.caption(f"Shoe #{sid}")
            c1, c2 = st.columns(2)
            
            if c1.button(f"{'👍 Liked' if is_up else '👍 Like'}", key=f"u_{sid}", type="primary" if is_up else "secondary", use_container_width=True):
                toggle_upvote(user, sid, 1 if is_up else 0)
                
            if c2.button(f"{'❤️ Fav' if is_fav else '🤍 Fav'}", key=f"f_{sid}", type="primary" if is_fav else "secondary", use_container_width=True):
                handle_favorite_click(user, sid, my_fav_id)

# --- LOGIN & MAIN ---
def login():
    st.markdown("<h1 style='text-align: center;'>👟 The Shoe Poll</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.container(border=True):
            tabs = st.tabs(["Voter", "Admin"])
            with tabs[0]:
                name = st.text_input("Name")
                email = st.text_input("Email")
                if st.button("Enter"):
                    if name and email:
                        st.session_state.update({'user_role': 'folk', 'user_id': email, 'user_name': name})
                        st.rerun()
            with tabs[1]:
                aid = st.text_input("Admin ID") 
                apass = st.text_input("Pass", type="password")
                if st.button("Login"):
                    if aid == "AK1130" and apass == "3110":
                        st.session_state.update({'user_role': 'admin', 'user_id': 'ADMIN', 'user_name': 'Admin'})
                        st.rerun()
                    else:
                        st.error("Invalid Credentials")

def main():
    init_db()
    if 'user_role' not in st.session_state:
        login()
    else:
        with st.sidebar:
            st.write(f"User: **{st.session_state.get('user_name')}**")
            if st.button("Logout"):
                st.session_state.clear()
                st.rerun()
        
        if st.session_state['user_role'] == 'admin':
            admin_dashboard()
        else:
            folks_gallery()

if __name__ == "__main__":
    main()
