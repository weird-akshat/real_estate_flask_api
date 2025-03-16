from flask import Flask, request, jsonify, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)

# Database connection function (thread-safe)
def db_connection():
    conn = None
    try:
        conn = sqlite3.connect("database.sqlite", check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    except sqlite3.Error as e:
        print(e)
    return conn

# Close the database connection at the end of each request
@app.route('/remove_favorite', methods=['DELETE'])
def remove_favorite():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        data = request.form  # Handle form-data requests too

    user_id = data.get('user_id')
    property_id = data.get('property_id')

    if not user_id or not property_id:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM favorites WHERE user_id = ? AND property_id = ?", (user_id, property_id))
            conn.commit()
        return jsonify({"message": "Property removed from favorites"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/delete_property/<int:property_id>', methods=['DELETE'])
def delete_property_by_id(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM properties WHERE property_id = ?", (property_id,))
            conn.commit()
        return jsonify({"message": "Property deleted successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

        return jsonify({"error": str(e)}), 500


@app.route('/get_offers/<int:property_id>', methods=['GET'])
def get_offers(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM offers WHERE property_id = ?", (property_id,))
            offers = cursor.fetchall()

        offer_list = [dict(offer) for offer in offers]
        return jsonify(offer_list), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


        
@app.route('/search_properties', methods=['GET'])
def search_properties():
    city = request.args.get('city')
    state = request.args.get('state')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    bedrooms = request.args.get('bedrooms')

    query = "SELECT * FROM properties WHERE 1=1"
    values = []

    if city:
        query += " AND city = ?"
        values.append(city)
    if state:
        query += " AND state = ?"
        values.append(state)
    if min_price:
        query += " AND price >= ?"
        values.append(min_price)
    if max_price:
        query += " AND price <= ?"
        values.append(max_price)
    if bedrooms:
        query += " AND bedrooms = ?"
        values.append(bedrooms)

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            properties = cursor.fetchall()

        property_list = [dict(property) for property in properties]
        return jsonify(property_list), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/get_properties_by_owner', methods=['GET'])
def get_properties_by_owner():
    owner_id = request.args.get('owner_id')

    if not owner_id:
        return jsonify({"error": "Missing owner_id"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM properties WHERE owner_id = ?", (owner_id,))
            properties = cursor.fetchall()

        property_list = [dict(property) for property in properties]
        return jsonify(property_list), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
@app.route('/update_property', methods=['PUT'])
def update_property():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        return jsonify({"error": "Invalid content type"}), 400

    property_id = data.get('property_id')
    if not property_id:
        return jsonify({"error": "Missing property_id"}), 400

    update_fields = []
    values = []

    allowed_fields = [
        "property_type", "area", "parking", "city", "state", "country",
        "price", "balcony", "bedrooms", "contact_number", "email",
        "description", "status"
    ]

    for field in allowed_fields:
        if field in data:
            update_fields.append(f"{field} = ?")
            values.append(data[field])

    if not update_fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(property_id)
    update_query = f"UPDATE properties SET {', '.join(update_fields)} WHERE property_id = ?"

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(update_query, values)
            conn.commit()
        return jsonify({"message": "Property updated successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
@app.route('/update_user', methods=['PUT'])
def update_user():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        return jsonify({"error": "Invalid content type"}), 400

    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    update_fields = []
    values = []

    allowed_fields = ["name", "email", "phone"]

    for field in allowed_fields:
        if field in data:
            update_fields.append(f"{field} = ?")
            values.append(data[field])

    if not update_fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(user_id)
    update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = ?"

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(update_query, values)
            conn.commit()
        return jsonify({"message": "User updated successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

# Function to create tables
def create_table():
    conn = db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, 
        name TEXT, 
        email TEXT, 
        phone TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS properties (
        property_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        owner_id TEXT, 
        property_type TEXT, 
        area TEXT, 
        parking TEXT, 
        city TEXT, 
        state TEXT, 
        country TEXT, 
        price TEXT, 
        balcony TEXT, 
        bedrooms TEXT, 
        contact_number TEXT, 
        email TEXT, 
        description TEXT, 
        status TEXT, 
        FOREIGN KEY (owner_id) REFERENCES users(user_id)
    );
    """)


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        visit_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        property_id INTEGER, 
        user_id TEXT, 
        status TEXT, 
        date_and_time TEXT, 
        FOREIGN KEY (user_id) REFERENCES users(user_id), 
        FOREIGN KEY (property_id) REFERENCES properties(property_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS images (
        image_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        property_id INTEGER, 
        image_url TEXT, 
        is_primary TEXT, 
        FOREIGN KEY (property_id) REFERENCES properties(property_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        user_id TEXT, 
        property_id TEXT,  
        FOREIGN KEY (property_id) REFERENCES properties(property_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS offers (
        offer_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        property_id INTEGER, 
        buyer_id TEXT, 
        amount REAL, 
        offer_status TEXT, 
        offer_date TEXT DEFAULT CURRENT_TIMESTAMP, 
        made_by TEXT CHECK(made_by IN ('buyer', 'owner')), 
        FOREIGN KEY (property_id) REFERENCES properties(property_id), 
        FOREIGN KEY (buyer_id) REFERENCES users(user_id)
    );
    """)

    conn.commit()

# Call table creation
with app.app_context():
    create_table()


UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 


@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files or 'property_id' not in request.form:
        return jsonify({"error": "Missing image or property_id"}), 400

    file = request.files['image']
    property_id = request.form['property_id']
    is_primary = request.form.get('is_primary', 'no')

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(f"{property_id}_{file.filename}")  # Rename for uniqueness
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO images (property_id, image_url, is_primary)
                VALUES (?, ?, ?)
            """, (property_id, file_path, is_primary))
            conn.commit()

        return jsonify({
            "message": "Image uploaded successfully",
            "image_url": request.host_url + file_path
        }), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_property_images', methods=['GET'])
def get_property_images():
    property_id = request.args.get('property_id')

    if not property_id:
        return jsonify({"error": "Missing property_id"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT image_url, is_primary FROM images WHERE property_id = ?", (property_id,))
            images = cursor.fetchall()

        image_list = [
            {
                "image_url": request.host_url + image["image_url"],
                "is_primary": image["is_primary"]
            }
            for image in images
        ]
        return jsonify(image_list), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


# CORS handling
@app.route('/make_offer', methods=['POST'])
def make_offer():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        data = request.form

    property_id = data.get('property_id')
    buyer_id = data.get('buyer_id')
    amount = data.get('amount')
    made_by = data.get('made_by')  # Must be "buyer" or "owner"

    if not property_id or not buyer_id or not amount or made_by not in ["buyer", "owner"]:
        return jsonify({"error": "Missing required fields or invalid made_by"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()

            # Ensure property exists
            cursor.execute("SELECT * FROM properties WHERE property_id = ?", (property_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Property not found"}), 404

            # Ensure user exists
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (buyer_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "User not found"}), 404

            # Insert offer with made_by field
            cursor.execute("""
                INSERT INTO offers (property_id, buyer_id, amount, offer_status, made_by) 
                VALUES (?, ?, ?, ?, ?)
            """, (property_id, buyer_id, amount, "Pending", made_by))

            conn.commit()
        return jsonify({"message": "Offer submitted successfully"}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/create_user', methods=['POST'])
def createUser():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        data = request.form  # Handle form-data requests too

    user_id = data.get('user_id')
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')

    if not user_id or not name or not email or not phone:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users VALUES (?,?,?,?)", (user_id, name, email, phone))
            conn.commit()
        return jsonify({"message": "User created successfully"}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/add_property', methods=['POST'])
def add_property():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        data = request.form

    owner_id = data.get('owner_id')
    property_type = data.get('property_type')
    area = data.get('area')
    parking = data.get('parking')
    city = data.get('city')
    state = data.get('state')
    country = data.get('country')
    price = data.get('price')
    balcony = data.get('balcony')
    bedrooms = data.get('bedrooms')
    contact_number = data.get('contact_number')
    email = data.get('email')
    description = data.get('description')
    status = data.get('status')

    if not all([owner_id, property_type, area, city, state, country, price, contact_number, email, status]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO properties (
                    owner_id, property_type, area, parking, city, state, country, price, 
                    balcony, bedrooms, contact_number, email, description, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (owner_id, property_type, area, parking, city, state, country, price, 
                  balcony, bedrooms, contact_number, email, description, status))
            conn.commit()
        return jsonify({"message": "Property added successfully"}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
@app.route('/get_property/<int:property_id>', methods=['GET'])
def get_property(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM properties WHERE property_id = ?", (property_id,))
            property_data = cursor.fetchone()
            
            if property_data is None:
                return jsonify({"error": "Property not found"}), 404

            return jsonify(dict(property_data)), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
@app.route('/add_favorite', methods=['POST'])
def add_favorite():
    if request.content_type == 'application/json':
        data = request.get_json()
    else:
        data = request.form  # Handle form-data requests too

    user_id = data.get('user_id')
    property_id = data.get('property_id')

    if not user_id or not property_id:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()

            # Check if the user exists
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "User not found"}), 404

            # Check if the property exists
            cursor.execute("SELECT * FROM properties WHERE property_id = ?", (property_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "Property not found"}), 404

            # Insert into favorites
            cursor.execute("""
                INSERT INTO favorites (user_id, property_id) VALUES (?, ?)
            """, (user_id, property_id))

            conn.commit()
        return jsonify({"message": "Property added to favorites"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Property already in favorites"}), 409
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
