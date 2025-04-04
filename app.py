from flask import Flask, request, jsonify, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS  # Import CORS
import os

app = Flask(__name__)

CORS(app)  

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
    user_id = request.args.get('user_id')  # ✅ Use query parameters
    property_id = request.args.get('property_id')

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


@app.route('/user/<user_id>', methods=['GET'])
def user_details(user_id):
    conn = db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if user:
        return jsonify(dict(user)), 200
    return jsonify({'error': 'User not found'}), 404
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

@app.route("/property_buyers/<int:property_id>", methods=["GET"])
def get_property_buyers(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT u.user_id, u.name, u.email, u.phone FROM users u
                JOIN offers o ON u.user_id = o.buyer_id
                WHERE o.property_id = ?
                """,
                (property_id,)
            )
            buyers = cursor.fetchall()
            
            if not buyers:
                return jsonify({"error": "No buyers found for this property"}), 404
            
            return jsonify([dict(buyer) for buyer in buyers]), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

        
@app.route('/search_properties', methods=['GET'])
def search_properties():
    city = request.args.get('city')
    state = request.args.get('state')
    min_price = request.args.get('min_price', type=int)
    max_price = request.args.get('max_price', type=int)
    bedrooms = request.args.get('bedrooms', type=int)
    area = request.args.get('area')
    bathrooms = request.args.get('bathrooms', type=int)
    parking = request.args.get('parking', type=int)
    balcony = request.args.get('balcony', type=int)

    query = "SELECT * FROM properties WHERE status = 'Available'"
    values = []

    if parking:
        query += " AND parking=?"
        values.append(parking)
    if balcony:
        query += " AND balcony=?"
        values.append(balcony)
    if bathrooms:
        query += " AND bathrooms=?"
        values.append(bathrooms)
    if city:
        query += " AND city=?"
        values.append(city)
    if area:
        query += " AND area=?"
        values.append(area)
    if state:
        query += " AND state=?"
        values.append(state)
    if min_price is not None:
        query += " AND price >= ?"
        values.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        values.append(max_price)
    if bedrooms is not None:
        query += " AND bedrooms=?"
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


@app.route('/update_visit_status/<int:visit_id>', methods=['PUT'])
def update_visit_status(visit_id):
    conn = db_connection()
    cursor = conn.cursor()

    # Update visit status to 'confirmed' where visit_id matches
    cursor.execute("""
        UPDATE visits
        SET status = 'confirmed'
        WHERE visit_id = ?
    """, (visit_id,))
    
    conn.commit()

    # Check if the update was successful
    if cursor.rowcount == 0:
        return jsonify({"error": "Visit not found"}), 404

    return jsonify({"message": "Visit status updated to confirmed"}), 200


@app.route('/accept_offer/<int:offer_id>', methods=['PUT'])
def accept_offer(offer_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM offers WHERE offer_id = ?", (offer_id,))
            offer = cursor.fetchone()
            if not offer:
                return jsonify({"error": "Offer not found"}), 404
            
            cursor.execute("UPDATE offers SET offer_status = 'Accepted' WHERE offer_id = ?", (offer_id,))
            conn.commit()

        return jsonify({"message": "Offer accepted successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user_offers/<string:user_id>", methods=["GET"])
def get_user_offers(user_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT p.*, i.image_url 
                FROM properties p
                JOIN offers o ON p.property_id = o.property_id
                LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                WHERE o.buyer_id = ?
                """,
                (user_id,)
            )
            properties = cursor.fetchall()
            
            if not properties:
                return jsonify({"error": "No properties found for this user"}), 404
            
            return jsonify([dict(property) for property in properties]), 200
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
        
@app.route('/delete_user/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()

            # Fetch the user details before deletion
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()

            if not user:
                return jsonify({"error": "User not found"}), 404

            user_data = dict(user)

            # Delete the user
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()

        return jsonify({"message": "User deleted successfully", "deleted_user": user_data}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500
@app.route('/is_property_sold/<int:property_id>', methods=['GET'])
def is_property_sold(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM properties WHERE property_id = ?", (property_id,))
            property_status = cursor.fetchone()

            if not property_status:
                return jsonify({"error": "Property not found"}), 404

            return jsonify({"property_id": property_id, "sold": property_status["status"].lower() == "sold"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/mark_property_sold/<int:property_id>', methods=['PUT'])
def mark_property_sold(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE properties SET status = 'sold' WHERE property_id = ?", (property_id,))
            conn.commit()

            if cursor.rowcount == 0:
                return jsonify({"error": "Property not found or already sold"}), 404

        return jsonify({"message": "Property marked as sold"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route("/offers/<string:buyer_id>/<int:property_id>", methods=["GET"])
def offers(buyer_id, property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM offers
                WHERE buyer_id = ? AND property_id = ?
                ORDER BY offer_date ASC
                """,
                (buyer_id, property_id),
            )
            offers = cursor.fetchall()
            
            if not offers:
                return jsonify({"error": "No offers found"}), 404
            
            return jsonify([dict(offer) for offer in offers]), 200
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
    data = request.get_json()
    
    user_id = data.get("user_id")
    name = data.get("name")
    phone = data.get("phone")

    if not user_id or not name or not phone:
        return jsonify({"error": "Missing required fields"}), 400

    conn = db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users 
        SET name = ?, phone = ? 
        WHERE user_id = ?
    """, (name, phone, user_id))

    conn.commit()
    conn.close()

    return jsonify({"message": "User updated successfully"}), 200
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
        name TEXT,
        owner_id TEXT, 
        property_type TEXT, 
        area TEXT, 
        parking TEXT, 
        city TEXT, 
        state TEXT, 
        country TEXT, 
        price REAL, 
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
        made_by TEXT,
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
@app.route('/upload_image', methods=['POST'])
def upload_image():
    print("Raw Request Data:", request.data)
    print("Request Content Type:", request.content_type)

    if 'image' not in request.files or 'property_id' not in request.form:
        return jsonify({"error": "Missing image or property_id"}), 400

    file = request.files['image']
    property_id = request.form['property_id']
    is_primary = request.form.get('is_primary', 'no')

    if not file or file.filename.strip() == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(f"{property_id}_{file.filename}")
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(file_path)
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
@app.route("/user/<string:user_id>/visited-properties", methods=["GET"])
def get_visited_properties(user_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT p.*, i.image_url 
                FROM properties p
                JOIN visits v ON p.property_id = v.property_id
                LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                WHERE v.user_id = ?
                """,
                (user_id,)
            )
            properties = cursor.fetchall()
            
            if not properties:
                return jsonify({"error": "No visited properties found for this user"}), 404
            
            return jsonify([dict(property) for property in properties]), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500





@app.route("/property/<int:property_id>/visitors", methods=["GET"])
def get_visitors(property_id):
    conn = db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT users.user_id, users.name, users.email, users.phone
        FROM users
        JOIN visits ON users.user_id = visits.user_id
        WHERE visits.property_id = ?
    """, (property_id,))
    
    visitors = [
        {"user_id": row[0], "name": row[1], "email": row[2], "phone": row[3]} 
        for row in cursor.fetchall()
    ]
    
    conn.close()
    return jsonify(visitors)

@app.route('/get_visits/<int:property_id>/<user_id>', methods=['GET'])
def get_visits(property_id, user_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM visits
                WHERE property_id = ? AND user_id = ?
                ORDER BY visit_id ASC
                """,
                (property_id, user_id)
            )
            visits = cursor.fetchall()
        
        if not visits:
            return jsonify({"error": "No visits found for this user and property"}), 404
        
        return jsonify([dict(visit) for visit in visits]), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_visit', methods=['POST'])
def add_visit():
    try:
        data = request.get_json()
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO visits (property_id, user_id, status, date_and_time, made_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (data['property_id'], data['user_id'], data['status'], data['date_and_time'], data['made_by'])
            )
            conn.commit()
        return jsonify({"message": "Visit added successfully"}), 201
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

@app.route('/get_favorite_properties/<string:user_id>', methods=['GET'])
def get_favorite_properties(user_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.* FROM properties p
                INNER JOIN favorites f ON p.property_id = f.property_id
                WHERE f.user_id = ?
            """, (user_id,))
            properties = cursor.fetchall()

        property_list = [dict(property) for property in properties]
        return jsonify(property_list), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500

# CORS handling
@app.route('/make_offer', methods=['POST'])
def make_offer():
    print("Raw Request Data:", request.data)
    print("Request Content Type:", request.content_type)

    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    print("Parsed Data:", data)

    required_fields = ["property_id", "buyer_id", "amount", "made_by"]
    missing_fields = [field for field in required_fields if not data.get(field)]

    if missing_fields or data["made_by"] not in ["buyer", "owner"]:
        return jsonify({"error": f"Missing required fields or invalid made_by: {', '.join(missing_fields)}"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM properties WHERE property_id = ?", (data["property_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "Property not found"}), 404

            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (data["buyer_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "User not found"}), 404

            cursor.execute("""
                INSERT INTO offers (property_id, buyer_id, amount, offer_status, made_by) 
                VALUES (?, ?, ?, ?, ?)
            """, (data["property_id"], data["buyer_id"], data["amount"], "Pending", data["made_by"]))

            conn.commit()
        return jsonify({"message": "Offer submitted successfully"}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/create_user', methods=['POST'])
def createUser():
    print("Raw Request Data:", request.data)  
    print("Request Content Type:", request.content_type)  

    try:
        data = request.get_json(force=True)  
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    print("Parsed Data:", data)  

    missing_fields = []
    for field in ["user_id", "name", "email", "phone"]:
        if not data.get(field):
            missing_fields.append(field)

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users VALUES (?,?,?,?)", 
                           (data['user_id'], data['name'], data['email'], data['phone']))
            conn.commit()
        return jsonify({"message": "User created successfully"}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/add_property', methods=['POST'])
def add_property():
    print("Raw Request Data:", request.data)
    print("Request Content Type:", request.content_type)

    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    print("Parsed Data:", data)

    required_fields = ["owner_id", "property_type", "area", "city", "state", "country", 
                       "price", "contact_number", "email", "status", "name"]
    missing_fields = [field for field in required_fields if field not in data or not data[field]]

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO properties (name, owner_id, property_type, area, parking, city, state, country, price, 
                                       balcony, bedrooms, contact_number, email, description, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['name'], data['owner_id'], data['property_type'], data['area'], data.get('parking'),
                  data['city'], data['state'], data['country'], data['price'], 
                  data.get('balcony'), data.get('bedrooms'), data['contact_number'], 
                  data['email'], data.get('description'), data['status']))
            property_id = cursor.lastrowid
            conn.commit()
        return jsonify({"message": "Property added successfully", "property_id": property_id}), 201
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
    print("Raw Request Data:", request.data)
    print("Request Content Type:", request.content_type)

    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    print("Parsed Data:", data)

    required_fields = ["user_id", "property_id"]
    missing_fields = [field for field in required_fields if not data.get(field)]

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        with db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (data["user_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "User not found"}), 404

            cursor.execute("SELECT 1 FROM properties WHERE property_id = ?", (data["property_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "Property not found"}), 404

            cursor.execute("INSERT INTO favorites (user_id, property_id) VALUES (?, ?)",
                           (data["user_id"], data["property_id"]))

            conn.commit()
        return jsonify({"message": "Property added to favorites"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Property already in favorites"}), 409
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
