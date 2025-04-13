from flask import Flask, request, jsonify, send_file
import os
import psycopg  # psycopg v3
from flask_cors import CORS
import base64
from io import BytesIO

app = Flask(__name__)
CORS(app)

# Get the database URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")

# Database connection function (thread-safe with psycopg connection pooling if needed)
def db_connection():
    return psycopg.connect(DATABASE_URL, autocommit=True)

@app.route('/remove_favorite', methods=['DELETE'])
def remove_favorite():
    user_id = request.args.get('user_id')
    property_id = request.args.get('property_id')

    if not user_id or not property_id:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM favorites WHERE user_id = %s AND property_id = %s", (user_id, property_id))
        return jsonify({"message": "Property removed from favorites"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete_property/<int:property_id>', methods=['DELETE'])
def delete_property_by_id(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM properties WHERE property_id = %s", (property_id,))
        return jsonify({"message": "Property deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/user/<user_id>', methods=['GET'])
def user_details(user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
                user = cursor.fetchone()
                if user:
                    colnames = [desc.name for desc in cursor.description]
                    return jsonify(dict(zip(colnames, user))), 200
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_offers/<int:property_id>', methods=['GET'])
def get_offers(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM offers WHERE property_id = %s", (property_id,))
                offers = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
                offer_list = [dict(zip(colnames, row)) for row in offers]
        return jsonify(offer_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/property_buyers/<int:property_id>", methods=["GET"])
def get_property_buyers(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT u.user_id, u.name, u.email, u.phone FROM users u
                    JOIN offers o ON u.user_id = o.buyer_id
                    WHERE o.property_id = %s
                    """,
                    (property_id,)
                )
                buyers = cursor.fetchall()
                if not buyers:
                    return jsonify({"error": "No buyers found for this property"}), 404
                colnames = [desc.name for desc in cursor.description]
                return jsonify([dict(zip(colnames, buyer)) for buyer in buyers]), 200
    except Exception as e:
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

    if parking is not None:
        query += " AND parking = %s"
        values.append(parking)
    if balcony is not None:
        query += " AND balcony = %s"
        values.append(balcony)
    if bathrooms is not None:
        query += " AND bathrooms = %s"
        values.append(bathrooms)
    if city:
        query += " AND city = %s"
        values.append(city)
    if area:
        query += " AND area = %s"
        values.append(area)
    if state:
        query += " AND state = %s"
        values.append(state)
    if min_price is not None:
        query += " AND price >= %s"
        values.append(min_price)
    if max_price is not None:
        query += " AND price <= %s"
        values.append(max_price)
    if bedrooms is not None:
        query += " AND bedrooms = %s"
        values.append(bedrooms)

    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, values)
                properties = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
                
                # Fetch primary image URLs for each property
                result = []
                for prop in properties:
                    prop_dict = dict(zip(colnames, prop))
                    
                    # Get primary image if available
                    cursor.execute(
                        "SELECT image_id FROM images WHERE property_id = %s AND is_primary = 'Yes' LIMIT 1", 
                        (prop_dict['property_id'],)
                    )
                    image = cursor.fetchone()
                    if image:
                        prop_dict['image_url'] = f"/get_image/{image[0]}"
                    
                    result.append(prop_dict)
                
                return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_visit_status/<int:visit_id>', methods=['PUT'])
def update_visit_status(visit_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE visits
                    SET status = 'confirmed'
                    WHERE visit_id = %s
                    """,
                    (visit_id,)
                )
                if cursor.rowcount == 0:
                    return jsonify({"error": "Visit not found"}), 404
        return jsonify({"message": "Visit status updated to confirmed"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/accept_offer/<int:offer_id>', methods=['PUT'])
def accept_offer(offer_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM offers WHERE offer_id = %s", (offer_id,))
                offer = cursor.fetchone()
                if not offer:
                    return jsonify({"error": "Offer not found"}), 404

                cursor.execute("UPDATE offers SET offer_status = 'Accepted' WHERE offer_id = %s", (offer_id,))
        return jsonify({"message": "Offer accepted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user_offers/<string:user_id>", methods=["GET"])
def get_user_offers(user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT p.*, i.image_id
                    FROM properties p
                    JOIN offers o ON p.property_id = o.property_id
                    LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                    WHERE o.buyer_id = %s
                    """,
                    (user_id,)
                )
                properties = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]

            if not properties:
                return jsonify({"error": "No properties found for this user"}), 404

            # Process the properties and add image URLs
            property_list = []
            for prop in properties:
                prop_dict = dict(zip(colnames, prop))
                if prop_dict['image_id']:
                    prop_dict['image_url'] = f"/get_image/{prop_dict['image_id']}"
                property_list.append(prop_dict)

            return jsonify(property_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_properties_by_owner', methods=['GET'])
def get_properties_by_owner():
    owner_id = request.args.get('owner_id')

    if not owner_id:
        return jsonify({"error": "Missing owner_id"}), 400

    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT p.*, i.image_id 
                    FROM properties p
                    LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                    WHERE p.owner_id = %s
                    """, 
                    (owner_id,)
                )
                properties = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
                
                # Add image URLs to properties
                result = []
                for prop in properties:
                    prop_dict = dict(zip(colnames, prop))
                    if prop_dict['image_id']:
                        prop_dict['image_url'] = f"/get_image/{prop_dict['image_id']}"
                    result.append(prop_dict)

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete_user/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                user = cursor.fetchone()

                if not user:
                    return jsonify({"error": "User not found"}), 404

                colnames = [desc.name for desc in cursor.description]
                user_data = dict(zip(colnames, user))

                cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        return jsonify({"message": "User deleted successfully", "deleted_user": user_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/is_property_sold/<int:property_id>', methods=['GET'])
def is_property_sold(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT status FROM properties WHERE property_id = %s", (property_id,))
                result = cursor.fetchone()

            if not result:
                return jsonify({"error": "Property not found"}), 404

            return jsonify({"property_id": property_id, "sold": result[0].lower() == "sold"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mark_property_sold/<int:property_id>', methods=['PUT'])
def mark_property_sold(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE properties SET status = 'sold' WHERE property_id = %s", (property_id,))
                if cursor.rowcount == 0:
                    return jsonify({"error": "Property not found or already sold"}), 404
        return jsonify({"message": "Property marked as sold"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/offers/<string:buyer_id>/<int:property_id>", methods=["GET"])
def offers(buyer_id, property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM offers
                    WHERE buyer_id = %s AND property_id = %s
                    ORDER BY offer_date ASC
                    """,
                    (buyer_id, property_id)
                )
                rows = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]

            if not rows:
                return jsonify({"error": "No offers found"}), 404
            
            return jsonify([dict(zip(colnames, row)) for row in rows]), 200
    except Exception as e:
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
            update_fields.append(f"{field} = %s")
            values.append(data[field])

    if not update_fields:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(property_id)
    update_query = f"UPDATE properties SET {', '.join(update_fields)} WHERE property_id = %s"

    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, values)
        return jsonify({"message": "Property updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_user', methods=['PUT'])
def update_user():
    data = request.get_json()
    
    user_id = data.get("user_id")
    name = data.get("name")
    phone = data.get("phone")

    if not user_id or not name or not phone:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users 
                    SET name = %s, phone = %s 
                    WHERE user_id = %s
                """, (name, phone, user_id))

        return jsonify({"message": "User updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def create_tables():
    conn = db_connection()
    with conn.cursor() as cursor:
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
            property_id SERIAL PRIMARY KEY, 
            name TEXT,
            owner_id TEXT, 
            property_type TEXT, 
            area TEXT, 
            parking TEXT, 
            city TEXT, 
            state TEXT, 
            country TEXT, 
            price DECIMAL, 
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
            visit_id SERIAL PRIMARY KEY, 
            property_id INTEGER, 
            user_id TEXT, 
            status TEXT, 
            date_and_time TIMESTAMPTZ, 
            made_by TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id), 
            FOREIGN KEY (property_id) REFERENCES properties(property_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            image_id SERIAL PRIMARY KEY,
            property_id INTEGER,
            image_data BYTEA,  -- Store the binary image data here
            is_primary TEXT,
            FOREIGN KEY (property_id) REFERENCES properties(property_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id TEXT, 
            property_id INTEGER,  
            FOREIGN KEY (property_id) REFERENCES properties(property_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            PRIMARY KEY (user_id, property_id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            offer_id SERIAL PRIMARY KEY, 
            property_id INTEGER, 
            buyer_id TEXT, 
            amount DECIMAL, 
            offer_status TEXT, 
            offer_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, 
            made_by TEXT CHECK(made_by IN ('buyer', 'owner')), 
            FOREIGN KEY (property_id) REFERENCES properties(property_id), 
            FOREIGN KEY (buyer_id) REFERENCES users(user_id)
        );
        """)

@app.route('/get_image/<int:image_id>', methods=['GET'])
def get_image(image_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT image_data FROM images WHERE image_id = %s", (image_id,))
                result = cursor.fetchone()
                
                if not result or not result[0]:
                    return jsonify({"error": "Image not found"}), 404
                
                # Create a file-like object from the binary data
                image_binary = result[0]
                image_io = BytesIO(image_binary)
                
                # Return the binary image data with appropriate content type
                # This is a simplification - in production you should detect the actual image type
                return send_file(image_io, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files or 'property_id' not in request.form:
        return jsonify({"error": "Missing image or property_id"}), 400

    file = request.files['image']
    property_id = request.form['property_id']
    is_primary = request.form.get('is_primary', 'No')

    if not file or file.filename.strip() == '':
        return jsonify({"error": "No selected file"}), 400

    # Read the image file as binary data
    image_data = file.read()

    try:
        # Store the image as binary data in PostgreSQL
        with db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if we're setting this as primary and other images exist
                if is_primary.lower() == 'yes':
                    # Update all existing images for this property to not be primary
                    cursor.execute(
                        "UPDATE images SET is_primary = 'No' WHERE property_id = %s",
                        (property_id,)
                    )

                # Insert the binary data of the image into the database
                cursor.execute("""
                    INSERT INTO images (property_id, image_data, is_primary)
                    VALUES (%s, %s, %s) RETURNING image_id
                """, (property_id, image_data, is_primary))
                
                image_id = cursor.fetchone()[0]

        return jsonify({
            "message": "Image uploaded successfully",
            "image_id": image_id,
            "image_url": f"/get_image/{image_id}"
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_property_images/<int:property_id>', methods=['GET'])
def get_property_images(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT image_id, is_primary FROM images WHERE property_id = %s", (property_id,))
                images = cursor.fetchall()

        if not images:
            return jsonify({"error": "No images found for this property"}), 404

        # Prepare the response with image URLs
        image_list = [
            {
                "image_id": image[0],
                "is_primary": image[1],
                "image_url": f"/get_image/{image[0]}"
            }
            for image in images
        ]

        return jsonify(image_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_visited_properties/<string:user_id>', methods=['GET'])
def get_visited_properties(user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT p.*, i.image_id 
                    FROM properties p
                    JOIN visits v ON p.property_id = v.property_id
                    LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                    WHERE v.user_id = %s
                    """,
                    (user_id,)
                )
                properties = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
                
            if not properties:
                return jsonify({"error": "No visited properties found for this user"}), 404

            # Add image URLs to properties
            property_list = []
            for prop in properties:
                prop_dict = dict(zip(colnames, prop))
                if prop_dict['image_id']:
                    prop_dict['image_url'] = f"/get_image/{prop_dict['image_id']}"
                property_list.append(prop_dict)
            
            return jsonify(property_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/property/<int:property_id>/visitors", methods=["GET"])
def get_visitors(property_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT users.user_id, users.name, users.email, users.phone
                    FROM users
                    JOIN visits ON users.user_id = visits.user_id
                    WHERE visits.property_id = %s
                """, (property_id,))
                
                rows = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
                visitors = [dict(zip(colnames, row)) for row in rows]
            
        return jsonify(visitors), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_visits/<int:property_id>/<user_id>', methods=['GET'])
def get_visits(property_id, user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM visits
                    WHERE property_id = %s AND user_id = %s
                    ORDER BY visit_id ASC
                    """,
                    (property_id, user_id)
                )
                visits = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]
        
        if not visits:
            return jsonify({"error": "No visits found for this user and property"}), 404
        
        return jsonify([dict(zip(colnames, visit)) for visit in visits]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_visit', methods=['POST'])
def add_visit():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['property_id', 'user_id', 'status', 'date_and_time', 'made_by']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO visits (property_id, user_id, status, date_and_time, made_by)
                    VALUES (%s, %s, %s, %s, %s) RETURNING visit_id
                    """,
                    (data['property_id'], data['user_id'], data['status'], 
                     data['date_and_time'], data['made_by'])
                )
                visit_id = cursor.fetchone()[0]
                
        return jsonify({"message": "Visit added successfully", "visit_id": visit_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_favorite_properties/<string:user_id>', methods=['GET'])
def get_favorite_properties(user_id):
    try:
        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT p.*, i.image_id 
                    FROM properties p
                    INNER JOIN favorites f ON p.property_id = f.property_id
                    LEFT JOIN images i ON p.property_id = i.property_id AND i.is_primary = 'Yes'
                    WHERE f.user_id = %s
                """, (user_id,))
                properties = cursor.fetchall()
                colnames = [desc.name for desc in cursor.description]

        # Add image URLs to properties
        property_list = []
        for prop in properties:
            prop_dict = dict(zip(colnames, prop))
            if prop_dict['image_id']:
                prop_dict['image_url'] = f"/get_image/{prop_dict['image_id']}"
            property_list.append(prop_dict)
                
        return jsonify(property_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/make_offer', methods=['POST'])
def make_offer():
    try:
        if request.content_type != 'application/json':
            data = request.get_json(force=True)
        else:
            data = request.get_json()

        required_fields = ["property_id", "buyer_id", "amount", "made_by"]
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields or data.get("made_by") not in ["buyer", "owner"]:
            return jsonify({"error": f"Missing required fields or invalid made_by: {', '.join(missing_fields)}"}), 400

        with db_connection() as conn:
            with conn.cursor() as cursor:
                # Verify property exists
                cursor.execute("SELECT 1 FROM properties WHERE property_id = %s", (data["property_id"],))
                if cursor.fetchone() is None:
                    return jsonify({"error": "Property not found"}), 404

                # Verify user exists
                cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (data["buyer_id"],))
                if cursor.fetchone() is None:
                    return jsonify({"error": "User not found"}), 404

                # Insert offer
                cursor.execute("""
                    INSERT INTO offers (property_id, buyer_id, amount, offer_status, made_by) 
                    VALUES (%s, %s, %s, %s, %s) RETURNING offer_id
                """, (data["property_id"], data["buyer_id"], data["amount"], "Pending", data["made_by"]))
                
                offer_id = cursor.fetchone()[0]

        return jsonify({
            "message": "Offer submitted successfully",
            "offer_id": offer_id
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_user', methods=['POST'])
def create_user():
    try:
        if request.content_type != 'application/json':
            data = request.get_json(force=True)
        else:
            data = request.get_json()

        required_fields = ["user_id", "name", "email", "phone"]
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        with db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (user_id, name, email, phone) VALUES (%s, %s, %s, %s)", 
                    (data['user_id'], data['name'], data['email'], data['phone'])
                )
                
        return jsonify({"message": "User created successfully"}), 201
    except Exception as e:
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
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO properties (name, owner_id, property_type, area, parking, city, state, country, price, 
                                          balcony, bedrooms, contact_number, email, description, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING property_id
                """, (data['name'], data['owner_id'], data['property_type'], data['area'], data.get('parking'),
                      data['city'], data['state'], data['country'], data['price'], 
                      data.get('balcony'), data.get('bedrooms'), data['contact_number'], 
                      data['email'], data.get('description'), data['status']))
                
                property_id = cursor.fetchone()[0]  # Get the property_id of the inserted row
                
        return jsonify({"message": "Property added successfully", "property_id": property_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/get_property/<int:property_id>', methods=['GET'])
def get_property(property_id):
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM properties WHERE property_id = %s", (property_id,))
            property_data = cursor.fetchone()
            
            if property_data is None:
                return jsonify({"error": "Property not found"}), 404

            # Convert the fetched row into a dictionary
            column_names = [desc[0] for desc in cursor.description]
            property_dict = dict(zip(column_names, property_data))

            return jsonify(property_dict), 200
    except psycopg2.Error as e:
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

            cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (data["user_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "User not found"}), 404

            cursor.execute("SELECT 1 FROM properties WHERE property_id = %s", (data["property_id"],))
            if cursor.fetchone() is None:
                return jsonify({"error": "Property not found"}), 404

            cursor.execute("INSERT INTO favorites (user_id, property_id) VALUES (%s, %s)",
                           (data["user_id"], data["property_id"]))

            conn.commit()
        return jsonify({"message": "Property added to favorites"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Property already in favorites"}), 409
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
if __name__ == "__main__":
    app.run(debug=True)
