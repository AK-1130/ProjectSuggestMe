import streamlit as st
import pandas as pd
import sqlite3
import os
import shutil
import io

# --- CONFIGURATION ---
st.set_page_config(page_title="Shoe Selection Pro", layout="wide")
DB_FILE = "shoes_v4.db"
IMAGE_FOLDER = "images"
ITEMS_PER_PAGE = 10

# Ensure local image directory exists
if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

# --- CSS FOR STANDARDIZED TILES ---
st.markdown("""
    <style>
    div[data-testid="stImage"] > img {
        height: 250px;  /* Fixed height for all images */
        width: 100%;
        object-fit: contain; /* Ensures image fits without stretching */
    }
    .stButton button {
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE MANAGEMENT ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS shoes 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  filename TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS votes 
                 (user_email TEXT, 
                  user_name TEXT,
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
        file_path = os.path.join(IMAGE_FOLDER, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
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
        os.remove(os.path.join(IMAGE_FOLDER, filename))
    except:
        pass

def delete_all_images():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM shoes")
    c.execute("DELETE FROM votes") # Optional: clear votes if images are gone
    conn.commit()
    conn.close()
    
    # Delete files
    for filename in os.listdir(IMAGE_FOLDER):
        file_path = os.path.join(IMAGE_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            st.error(f"Failed to delete {file_path}. Reason: {e}")

def delete_user_response(user_email):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM votes WHERE user_email = ?", (user_email,))
    conn.commit()
    conn.close()

# --- VOTING LOGIC ---
@st.dialog("Change Favorite Shoe?")
def confirm_switch_favorite(user_email, user_name, new_shoe_id, old_shoe_id):
    st.write(f"You have a favorite (Shoe #{old_shoe_id}). Switch to this one?")
    col1, col2 = st.columns(2)
    if col1.button("Yes, Switch"):
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, old_shoe_id))
        c.execute("""INSERT INTO votes (user_email, user_name, shoe_id, is_favorite) VALUES (?, ?, ?, 1)
                     ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", (user_email, user_name, new_shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    if col2.button("No"):
        st.rerun()

def toggle_upvote(user_email, user_name, shoe_id, current_status):
    new_status = 0 if current_status == 1 else 1
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO votes (user_email, user_name, shoe_id, upvoted) VALUES (?, ?, ?, ?)
                 ON CONFLICT(user_email, shoe_id) DO UPDATE SET upvoted = ?""",
              (user_email, user_name, shoe_id, new_status, new_status))
    conn.commit()
    conn.close()
    st.rerun()

def handle_favorite_click(user_email, user_name, shoe_id, current_fav_id):
    conn = get_db()
    c = conn.cursor()
    if current_fav_id == shoe_id: 
        c.execute("UPDATE votes SET is_favorite = 0 WHERE user_email = ? AND shoe_id = ?", (user_email, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    elif current_fav_id is None: 
        c.execute("""INSERT INTO votes (user_email, user_name, shoe_id, is_favorite) VALUES (?, ?, ?, 1)
                     ON CONFLICT(user_email, shoe_id) DO UPDATE SET is_favorite = 1""", (user_email, user_name, shoe_id))
        conn.commit()
        conn.close()
        st.rerun()
    else: 
        conn.close()
        confirm_switch_favorite(user_email, user_name, shoe_id, current_fav_id)

# --- ADMIN PAGE ---
def admin_dashboard():
    st.title("Admin Dashboard 🛠️")
    
    tabs = st.tabs(["📤 Upload", "🗑️ Manage Images", "👥 User Responses", "📊 Stats"])
    
    # TAB 1: UPLOAD
    with tabs[0]:
        st.subheader("Bulk Upload")
        uploaded_files = st.file_uploader("Choose photos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'webp'])
        if uploaded_files:
            if st.button(f"Save {len(uploaded_files)} Photos"):
                count = save_uploaded_files(uploaded_files)
                st.success(f"Saved {count} images!")
                st.rerun()

    # TAB 2: MANAGE IMAGES
    with tabs[1]:
        col_head_1, col_head_2 = st.columns([3, 1])
        with col_head_1:
            st.subheader("Gallery Management")
        with col_head_2:
            if st.button("🚨 DELETE ALL IMAGES", type="primary"):
                delete_all_images()
                st.rerun()

        conn = get_db()
        all_shoes = pd.read_sql("SELECT * FROM shoes", conn)
        conn.close()
        
        if all_shoes.empty:
            st.warning("No images found.")
        else:
            # Pagination Logic
            total_items = len(all_shoes)
            total_pages = max(1, (total_items - 1) // ITEMS_PER_PAGE + 1)
            
            if 'admin_page' not in st.session_state:
                st.session_state.admin_page = 1
                
            col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
            with col_p1:
                if st.button("Previous") and st.session_state.admin_page > 1:
                    st.session_state.admin_page -= 1
                    st.rerun()
            with col_p2:
                st.write(f"Page {st.session_state.admin_page} of {total_pages}")
            with col_p3:
                if st.button("Next") and st.session_state.admin_page < total_pages:
                    st.session_state.admin_page += 1
                    st.rerun()
            
            # Slice Data
            start_idx = (st.session_state.admin_page - 1) * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            page_shoes = all_shoes.iloc[start_idx:end_idx]

            cols = st.columns(5) # 5 cols grid
            for idx, row in page_shoes.iterrows():
                with cols[idx % 5]:
                    st.container(border=True)
                    img_path = os.path.join(IMAGE_FOLDER, row['filename'])
                    if os.path.exists(img_path):
                        st.image(img_path)
                    st.caption(f"ID: {row['id']}")
                    if st.button("Del", key=f"del_{row['id']}"):
                        delete_shoe(row['id'], row['filename'])
                        st.rerun()

    # TAB 3: USER RESPONSES
    with tabs[2]:
        st.subheader("User Responses Database")
        conn = get_db()
        # Fetch raw votes
        votes_df = pd.read_sql("SELECT user_name, user_email, shoe_id, upvoted, is_favorite FROM votes", conn)
        conn.close()

        if not votes_df.empty:
            # Pivot table for better viewing: One row per user
            # This is complex because users vote on many items. 
            # Simplified View: List of Users and their Action count
            
            user_summary = votes_df.groupby(['user_name', 'user_email']).agg({
                'upvoted': 'sum',
                'is_favorite': 'sum'
            }).reset_index()
            
            st.dataframe(user_summary)

            c1, c2 = st.columns(2)
            with c1:
                # Export to Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    votes_df.to_excel(writer, index=False, sheet_name='Raw Data')
                    user_summary.to_excel(writer, index=False, sheet_name='Summary')
                
                st.download_button(
                    label="📥 Download as Excel",
                    data=buffer.getvalue(),
                    file_name="shoe_votes.xlsx",
                    mime="application/vnd.ms-excel"
                )

            with c2:
                # Delete specific user
                user_to_del = st.selectbox("Select User to Delete", user_summary['user_email'].unique())
                if st.button(f"Delete responses from {user_to_del}"):
                    delete_user_response(user_to_del)
                    st.success("Deleted.")
                    st.rerun()
        else:
            st.info("No responses yet.")

    # TAB 4: STATS
    with tabs[3]:
        st.subheader("Live Stats")
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
            st.bar_chart(stats.set_index('id')['ups'])
            st.dataframe(stats)

# --- FOLKS PAGE ---
def folks_gallery():
    user = st.session_state['user_id']
    user_name = st.session_state['user_name']
    st.title(f"Welcome, {user_name}!")
    
    conn = get_db()
    
    # User Votes
    my_votes = pd.read_sql("SELECT * FROM votes WHERE user_email = ?", conn, params=(user,))
    my_ups = my_votes[my_votes['upvoted'] == 1]['shoe_id'].tolist()
    fav_row = my_votes[my_votes['is_favorite'] == 1]
    my_fav_id = fav_row.iloc[0]['shoe_id'] if not fav_row.empty else None

    # Get Shoes
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

    # Pagination for Folks
    total_items = len(shoes)
    total_pages = max(1, (total_items - 1) // ITEMS_PER_PAGE + 1)
    
    if 'folk_page' not in st.session_state:
        st.session_state.folk_page = 1
        
    # Slicing
    start_idx = (st.session_state.folk_page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_shoes = shoes.iloc[start_idx:end_idx]

    # Grid Display
    cols = st.columns(5) # 5 items per row
    for idx, row in page_shoes.iterrows():
        sid = row['id']
        fname = row['filename']
        img_path = os.path.join(IMAGE_FOLDER, fname)
        
        is_up = sid in my_ups
        is_fav = (sid == my_fav_id)
        
        with cols[idx % 5]:
            st.container(border=True)
            if os.path.exists(img_path):
                st.image(img_path)
            
            st.caption(f"#{sid}")
            c1, c2 = st.columns(2)
            
            if c1.button(f"{'👍' if is_up else 'Like'}", key=f"u_{sid}", type="primary" if is_up else "secondary"):
                toggle_upvote(user, user_name, sid, 1 if is_up else 0)
                
            if c2.button(f"{'❤️' if is_fav else 'Fav'}", key=f"f_{sid}", type="primary" if is_fav else "secondary"):
                handle_favorite_click(user, user_name, sid, my_fav_id)

    # Navigation Buttons
    st.divider()
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.button("⬅️ Previous") and st.session_state.folk_page > 1:
            st.session_state.folk_page -= 1
            st.rerun()
    with c2:
        st.markdown(f"<h4 style='text-align: center;'>Page {st.session_state.folk_page} of {total_pages}</h4>", unsafe_allow_html=True)
    with c3:
        if st.button("Next ➡️") and st.session_state.folk_page < total_pages:
            st.session_state.folk_page += 1
            st.rerun()

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
                aid = st.text_input("ID")
                apass = st.text_input("Pass", type="password")
                if st.button("Login"):
                    if aid == "AK1130" and apass == "3110":
                        st.session_state.update({'user_role': 'admin', 'user_id': 'ADMIN', 'user_name': 'Admin'})
                        st.rerun()

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
