from flask import Flask, request, jsonify, g, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_cors import CORS
import os
import io
import base64

app = Flask(__name__)

CORS(app)

# Database connection function
def db_connection():
    conn = None
    try:
        # Get database URL from environment variable for Render
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            # Supabase database connection string
            database_url = "postgresql://postgres:rems@db.cmhffuysnjuhrltzlapq.supabase.co:5432/postgres"
        
        conn = psycopg2.connect(database_url)
        conn.autocommit = False  # For transaction control
    except psycopg2.Error as e:
        print(e)
    return conn

# Create tables function
def create_tables():
    conn = db_connection()
    cursor = conn.cursor()
    cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, 
    name TEXT NOT NULL, 
    email TEXT NOT NULL, 
    phone TEXT NOT NULL
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS properties (
    property_id SERIAL PRIMARY KEY, 
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL, 
    property_type TEXT NOT NULL, 
    area TEXT NOT NULL, 
    parking TEXT NOT NULL, 
    city TEXT NOT NULL, 
    state TEXT NOT NULL, 
    country TEXT NOT NULL, 
    price FLOAT NOT NULL, 
    balcony TEXT,
    bedrooms TEXT NOT NULL, 
    contact_number TEXT NOT NULL, 
    email TEXT NOT NULL, 
    description TEXT,
    status TEXT NOT NULL, 
    FOREIGN KEY (owner_id) REFERENCES users(user_id)
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS visits (
    visit_id SERIAL PRIMARY KEY, 
    property_id INTEGER NOT NULL, 
    user_id TEXT NOT NULL, 
    status TEXT NOT NULL, 
    date_and_time TEXT NOT NULL, 
    made_by TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id), 
    FOREIGN KEY (property_id) REFERENCES properties(property_id)
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS images (
    image_id SERIAL PRIMARY KEY, 
    property_id INTEGER NOT NULL, 
    image_data BYTEA NOT NULL, 
    image_type TEXT NOT NULL,
    is_primary TEXT NOT NULL, 
    FOREIGN KEY (property_id) REFERENCES properties(property_id)
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS favorites (
    user_id TEXT NOT NULL, 
    property_id INTEGER NOT NULL,  
    FOREIGN KEY (property_id) REFERENCES properties(property_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    PRIMARY KEY (user_id, property_id)
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS offers (
    offer_id SERIAL PRIMARY KEY, 
    property_id INTEGER NOT NULL, 
    buyer_id TEXT NOT NULL, 
    amount FLOAT NOT NULL, 
    offer_status TEXT NOT NULL, 
    offer_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
    made_by TEXT NOT NULL CHECK(made_by IN ('buyer', 'owner')), 
    FOREIGN KEY (property_id) REFERENCES properties(property_id), 
    FOREIGN KEY (buyer_id) REFERENCES users(user_id)
);
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS operation_logs (
    log_id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    user_id TEXT,
    operation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);
""")

    # Create PL/pgSQL procedures
    # Procedure 1: Add or update user
    cursor.execute("""
    CREATE OR REPLACE PROCEDURE upsert_user(
        p_user_id TEXT,
        p_name TEXT,
        p_email TEXT,
        p_phone TEXT
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
        -- Check if user exists
        IF EXISTS (SELECT 1 FROM users WHERE user_id = p_user_id) THEN
            -- Update existing user
            UPDATE users 
            SET name = p_name, phone = p_phone
            WHERE user_id = p_user_id;
        ELSE
            -- Insert new user
            INSERT INTO users (user_id, name, email, phone)
            VALUES (p_user_id, p_name, p_email, p_phone);
        END IF;
    END;
    $$;
    """)

    # Procedure 2: Add property with validation
    cursor.execute("""
    CREATE OR REPLACE PROCEDURE add_property_proc(
        p_name TEXT,
        p_owner_id TEXT,
        p_property_type TEXT,
        p_area TEXT,
        p_parking TEXT,
        p_city TEXT,
        p_state TEXT,
        p_country TEXT,
        p_price FLOAT,
        p_balcony TEXT,
        p_bedrooms TEXT,
        p_contact_number TEXT,
        p_email TEXT,
        p_description TEXT,
        p_status TEXT,
        INOUT p_property_id INTEGER DEFAULT NULL
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
        -- Validate owner existence
        IF NOT EXISTS (SELECT 1 FROM users WHERE user_id = p_owner_id) THEN
            RAISE EXCEPTION 'Owner with ID % does not exist', p_owner_id;
        END IF;
        
        -- Validate price
        IF p_price <= 0 THEN
            RAISE EXCEPTION 'Price must be greater than zero';
        END IF;
        
        -- Insert the property
        INSERT INTO properties (
            name, owner_id, property_type, area, parking, city, 
            state, country, price, balcony, bedrooms, 
            contact_number, email, description, status
        ) VALUES (
            p_name, p_owner_id, p_property_type, p_area, p_parking, p_city,
            p_state, p_country, p_price, p_balcony, p_bedrooms,
            p_contact_number, p_email, p_description, p_status
        ) RETURNING property_id INTO p_property_id;
    END;
    $$;
    """)

    # Procedure 3: Process property offer
    cursor.execute("""
    CREATE OR REPLACE PROCEDURE process_offer(
        p_property_id INTEGER,
        p_buyer_id TEXT,
        p_amount FLOAT,
        p_made_by TEXT,
        INOUT p_offer_id INTEGER DEFAULT NULL
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
        -- Validate property
        IF NOT EXISTS (SELECT 1 FROM properties WHERE property_id = p_property_id) THEN
            RAISE EXCEPTION 'Property with ID % does not exist', p_property_id;
        END IF;
        
        -- Validate buyer
        IF NOT EXISTS (SELECT 1 FROM users WHERE user_id = p_buyer_id) THEN
            RAISE EXCEPTION 'User with ID % does not exist', p_buyer_id;
        END IF;
        
        -- Validate amount
        IF p_amount <= 0 THEN
            RAISE EXCEPTION 'Offer amount must be greater than zero';
        END IF;
        
        -- Check if property is available
        IF EXISTS (SELECT 1 FROM properties WHERE property_id = p_property_id AND status = 'sold') THEN
            RAISE EXCEPTION 'Cannot make offer on sold property';
        END IF;
        
        -- Create the offer
        INSERT INTO offers (property_id, buyer_id, amount, offer_status, made_by)
        VALUES (p_property_id, p_buyer_id, p_amount, 'Pending', p_made_by)
        RETURNING offer_id INTO p_offer_id;
    END;
    $$;
    """)

    # Procedure 4: Handle property sale
    cursor.execute("""
    CREATE OR REPLACE PROCEDURE sell_property(
        p_property_id INTEGER,
        p_offer_id INTEGER
    )
    LANGUAGE plpgsql
    AS $$
    DECLARE
        v_property_exists BOOLEAN;
        v_offer_exists BOOLEAN;
    BEGIN
        -- Check if property exists
        SELECT EXISTS(SELECT 1 FROM properties WHERE property_id = p_property_id) INTO v_property_exists;
        IF NOT v_property_exists THEN
            RAISE EXCEPTION 'Property with ID % does not exist', p_property_id;
        END IF;
        
        -- Check if offer exists
        SELECT EXISTS(SELECT 1 FROM offers WHERE offer_id = p_offer_id AND property_id = p_property_id) INTO v_offer_exists;
        IF NOT v_offer_exists THEN
            RAISE EXCEPTION 'Offer with ID % for property % does not exist', p_offer_id, p_property_id;
        END IF;
        
        -- Update property status
        UPDATE properties SET status = 'sold' WHERE property_id = p_property_id;
        
        -- Update offer status
        UPDATE offers SET offer_status = 'Accepted' WHERE offer_id = p_offer_id;
        
        -- Reject other offers for this property
        UPDATE offers 
        SET offer_status = 'Rejected' 
        WHERE property_id = p_property_id AND offer_id != p_offer_id AND offer_status = 'Pending';
    END;
    $$;
    """)

    # Create trigger for logging property status changes
    cursor.execute("""
    CREATE OR REPLACE FUNCTION log_property_status_change()
    RETURNS TRIGGER AS $$
    BEGIN
        IF OLD.status IS DISTINCT FROM NEW.status THEN
            INSERT INTO operation_logs (
                table_name, operation_type, record_id, details
            ) VALUES (
                'properties', 'status_change', NEW.property_id::TEXT,
                'Status changed from ' || COALESCE(OLD.status, 'NULL') || ' to ' || COALESCE(NEW.status, 'NULL')
            );
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    cursor.execute("""
    DROP TRIGGER IF EXISTS property_status_change_trigger ON properties;
    CREATE TRIGGER property_status_change_trigger
    AFTER UPDATE ON properties
    FOR EACH ROW
    EXECUTE FUNCTION log_property_status_change();
    """)

    # Create trigger for logging new offers
    cursor.execute("""
    CREATE OR REPLACE FUNCTION log_new_offer()
    RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO operation_logs (
            table_name, operation_type, record_id, user_id, details
        ) VALUES (
            'offers', 'new_offer', NEW.offer_id::TEXT, NEW.buyer_id,
            'New offer of $' || NEW.amount::TEXT || ' for property ID ' || NEW.property_id::TEXT
        );
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    cursor.execute("""
    DROP TRIGGER IF EXISTS new_offer_trigger ON offers;
    CREATE TRIGGER new_offer_trigger
    AFTER INSERT ON offers
    FOR EACH ROW
    EXECUTE FUNCTION log_new_offer();
    """)

    conn.commit()
    conn.close()

# Initialize tables
with app.app_context():
    create_tables()

@app.route('/remove_favorite', methods=['DELETE'])
def remove_favorite():
    user_id = request.args.get('user_id')
    property_id = request.args.get('property_id')

    if not user_id or not property_id:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE user_id = %s AND property_id = %s", (user_id, property_id))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Property removed from favorites"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/user/<user_id>', methods=['GET'])
def user_details(user_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return jsonify(dict(user)), 200
        return jsonify({'error': 'User not found'}), 404
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_offers/<int:property_id>', methods=['GET'])
def get_offers(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM offers WHERE property_id = %s", (property_id,))
        offers = cursor.fetchall()
        conn.close()

        offer_list = [dict(offer) for offer in offers]
        return jsonify(offer_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/property_buyers/<int:property_id>", methods=["GET"])
def get_property_buyers(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT DISTINCT u.user_id, u.name, u.email, u.phone FROM users u
            JOIN offers o ON u.user_id = o.buyer_id
            WHERE o.property_id = %s
            """,
            (property_id,)
        )
        buyers = cursor.fetchall()
        conn.close()
        
        if not buyers:
            return jsonify({"error": "No buyers found for this property"}), 404
        
        return jsonify([dict(buyer) for buyer in buyers]), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search_properties', methods=['GET'])
def search_properties():
    city = request.args.get('city')
    state = request.args.get('state')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    bedrooms = request.args.get('bedrooms', type=int)
    area = request.args.get('area')
    bathrooms = request.args.get('bathrooms', type=int)
    parking = request.args.get('parking', type=int)
    balcony = request.args.get('balcony', type=int)

    query = "SELECT * FROM properties WHERE status = 'Available'"
    values = []

    if parking:
        query += " AND parking=%s"
        values.append(parking)
    if balcony:
        query += " AND balcony=%s"
        values.append(balcony)
    if bathrooms:
        query += " AND bathrooms=%s"
        values.append(bathrooms)
    if city:
        query += " AND city=%s"
        values.append(city)
    if area:
        query += " AND area=%s"
        values.append(area)
    if state:
        query += " AND state=%s"
        values.append(state)
    if min_price is not None:
        query += " AND price >= %s"
        values.append(min_price)
    if max_price is not None:
        query += " AND price <= %s"
        values.append(max_price)
    if bedrooms is not None:
        query += " AND bedrooms=%s"
        values.append(bedrooms)

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, values)
        properties = cursor.fetchall()
        conn.close()

        property_list = [dict(prop) for prop in properties]
        return jsonify(property_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_visit_status/<int:visit_id>', methods=['PUT'])
def update_visit_status(visit_id):
    try:
        conn = db_connection()
        cursor = conn.cursor()

        # Update visit status to 'confirmed' where visit_id matches
        cursor.execute("""
            UPDATE visits
            SET status = 'confirmed'
            WHERE visit_id = %s
        """, (visit_id,))
        
        conn.commit()
        
        # Check if the update was successful
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({"error": "Visit not found"}), 404
            
        conn.close()
        return jsonify({"message": "Visit status updated to confirmed"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/accept_offer/<int:offer_id>', methods=['PUT'])
def accept_offer(offer_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get the property_id for the offer
        cursor.execute("SELECT property_id FROM offers WHERE offer_id = %s", (offer_id,))
        offer = cursor.fetchone()
        if not offer:
            conn.close()
            return jsonify({"error": "Offer not found"}), 404
        
        property_id = offer['property_id']
        
        # Use the stored procedure to accept the offer and mark property as sold
        cursor.execute("CALL sell_property(%s, %s)", (property_id, offer_id))
        conn.commit()
        conn.close()

        return jsonify({"message": "Offer accepted successfully and property marked as sold"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user_offers/<string:user_id>", methods=["GET"])
def get_user_offers(user_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query properties with offers but without retrieving images
        cursor.execute(
            """
            SELECT DISTINCT p.* 
            FROM properties p
            JOIN offers o ON p.property_id = o.property_id
            WHERE o.buyer_id = %s
            """,
            (user_id,)
        )
        properties = cursor.fetchall()
        
        if not properties:
            conn.close()
            return jsonify({"error": "No properties found for this user"}), 404
        
        # For each property, get its primary image
        property_list = []
        for prop in properties:
            property_dict = dict(prop)
            
            # Get primary image for this property
            cursor.execute(
                """
                SELECT image_id FROM images 
                WHERE property_id = %s AND is_primary = 'Yes' 
                LIMIT 1
                """, 
                (prop['property_id'],)
            )
            image_result = cursor.fetchone()
            
            if image_result:
                property_dict['image_id'] = image_result['image_id']
            
            property_list.append(property_dict)
        
        conn.close()
        return jsonify(property_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_properties_by_owner', methods=['GET'])
def get_properties_by_owner():
    owner_id = request.args.get('owner_id')

    if not owner_id:
        return jsonify({"error": "Missing owner_id"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM properties WHERE owner_id = %s", (owner_id,))
        properties = cursor.fetchall()
        conn.close()

        property_list = [dict(prop) for prop in properties]
        return jsonify(property_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/is_property_sold/<int:property_id>', methods=['GET'])
def is_property_sold(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT status FROM properties WHERE property_id = %s", (property_id,))
        property_status = cursor.fetchone()
        conn.close()

        if not property_status:
            return jsonify({"error": "Property not found"}), 404

        return jsonify({"property_id": property_id, "sold": property_status["status"].lower() == "sold"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mark_property_sold/<int:property_id>', methods=['PUT'])
def mark_property_sold(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor()
        # This update will trigger the property_status_change_trigger
        cursor.execute("UPDATE properties SET status = 'sold' WHERE property_id = %s", (property_id,))
        conn.commit()

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({"error": "Property not found or already sold"}), 404

        conn.close()
        return jsonify({"message": "Property marked as sold"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/offers/<string:buyer_id>/<int:property_id>", methods=["GET"])
def offers(buyer_id, property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT * FROM offers
            WHERE buyer_id = %s AND property_id = %s
            ORDER BY offer_date ASC
            """,
            (buyer_id, property_id),
        )
        offers = cursor.fetchall()
        conn.close()
        
        if not offers:
            return jsonify({"error": "No offers found"}), 404
        
        return jsonify([dict(offer) for offer in offers]), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_user', methods=['PUT'])
def update_user():
    data = request.get_json()
    
    user_id = data.get("user_id")
    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email", "")  # Add email with default empty value

    if not user_id or not name or not phone:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()
        
        # Use the stored procedure to update user
        cursor.execute("CALL upsert_user(%s, %s, %s, %s)", (user_id, name, email, phone))
        conn.commit()
        conn.close()

        return jsonify({"message": "User updated successfully"}), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

# New endpoint to get image directly
@app.route('/get_image/<int:image_id>', methods=['GET'])
def get_image(image_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT image_data, image_type FROM images WHERE image_id = %s", (image_id,))
        image = cursor.fetchone()
        conn.close()

        if not image:
            return jsonify({"error": "Image not found"}), 404

        # Create in-memory binary stream
        img_io = io.BytesIO(image['image_data'])
        img_io.seek(0)
        
        # Return the binary data as a file
        return send_file(img_io, mimetype=image['image_type'])
    except psycopg2.Error as e:
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

    try:
        # Read image binary data
        image_data = file.read()
        image_type = file.content_type
        
        conn = db_connection()
        cursor = conn.cursor()
        
        # Store binary data directly in the database
        cursor.execute("""
            INSERT INTO images (property_id, image_data, image_type, is_primary)
            VALUES (%s, %s, %s, %s) RETURNING image_id
        """, (property_id, psycopg2.Binary(image_data), image_type, is_primary))
        
        image_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        return jsonify({
            "message": "Image uploaded successfully",
            "image_id": image_id
        }), 201
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user/<string:user_id>/visited-properties", methods=["GET"])
def get_visited_properties(user_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query properties with visits but without retrieving images
        cursor.execute(
            """
            SELECT DISTINCT p.* 
            FROM properties p
            JOIN visits v ON p.property_id = v.property_id
            WHERE v.user_id = %s
            """,
            (user_id,)
        )
        properties = cursor.fetchall()
        
        if not properties:
            conn.close()
            return jsonify({"error": "No visited properties found for this user"}), 404
        
        # For each property, get its primary image
        property_list = []
        for prop in properties:
            property_dict = dict(prop)
            
            # Get primary image for this property
            cursor.execute(
                """
                SELECT image_id FROM images 
                WHERE property_id = %s AND is_primary = 'Yes' 
                LIMIT 1
                """, 
                (prop['property_id'],)
            )
            image_result = cursor.fetchone()
            
            if image_result:
                property_dict['image_id'] = image_result['image_id']
            
            property_list.append(property_dict)
        
        conn.close()
        return jsonify(property_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route("/property/<int:property_id>/visitors", methods=["GET"])
def get_visitors(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DISTINCT u.user_id, u.name, u.email, u.phone
            FROM users u
            JOIN visits v ON u.user_id = v.user_id
            WHERE v.property_id = %s
        """, (property_id,))
        
        visitors = cursor.fetchall()
        conn.close()
        
        return jsonify([dict(visitor) for visitor in visitors]), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_visits/<int:property_id>/<user_id>', methods=['GET'])
def get_visits(property_id, user_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT * FROM visits
            WHERE property_id = %s AND user_id = %s
            ORDER BY visit_id ASC
            """,
            (property_id, user_id)
        )
        visits = cursor.fetchall()
        conn.close()
        
        if not visits:
            return jsonify({"error": "No visits found for this user and property"}), 404
        
        return jsonify([dict(visit) for visit in visits]), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_visit', methods=['POST'])
def add_visit():
    try:
        data = request.get_json()
        conn = db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO visits (property_id, user_id, status, date_and_time, made_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (data['property_id'], data['user_id'], data['status'], data['date_and_time'], data['made_by'])
        )
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Visit added successfully"}), 201
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_property_images', methods=['GET'])
def get_property_images():
    property_id = request.args.get('property_id')

    if not property_id:
        return jsonify({"error": "Missing property_id"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT image_id, is_primary FROM images WHERE property_id = %s", (property_id,))
        images = cursor.fetchall()
        conn.close()

        image_list = [
            {
                "image_id": image["image_id"],
                "is_primary": image["is_primary"],
                "image_url": f"/get_image/{image['image_id']}"
            }
            for image in images
        ]
        return jsonify(image_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_favorite_properties/<string:user_id>', methods=['GET'])
def get_favorite_properties(user_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT p.* FROM properties p
            INNER JOIN favorites f ON p.property_id = f.property_id
            WHERE f.user_id = %s
        """, (user_id,))
        properties = cursor.fetchall()
        conn.close()

        property_list = [dict(prop) for prop in properties]
        return jsonify(property_list), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/make_offer', methods=['POST'])
def make_offer():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    required_fields = ["property_id", "buyer_id", "amount", "made_by"]
    missing_fields = [field for field in required_fields if not data.get(field)]

    if missing_fields or data["made_by"] not in ["buyer", "owner"]:
        return jsonify({"error": f"Missing required fields or invalid made_by: {', '.join(missing_fields)}"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()

        # Use the stored procedure to process offer
        offer_id = None
        cursor.execute(
            "CALL process_offer(%s, %s, %s, %s, %s)",
            (data["property_id"], data["buyer_id"], data["amount"], data["made_by"], offer_id)
        )
        
        # Get the returned offer_id
        offer_id = cursor.fetchone()[0] if cursor.description else None
        
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Offer submitted successfully", "offer_id": offer_id}), 201
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create_user', methods=['POST'])
def createUser():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    missing_fields = []
    for field in ["user_id", "name", "email", "phone"]:
        if not data.get(field):
            missing_fields.append(field)

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()
        
        # Use the stored procedure for user creation
        cursor.execute(
            "CALL upsert_user(%s, %s, %s, %s)",
            (data['user_id'], data['name'], data['email'], data['phone'])
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({"message": "User created successfully"}), 201
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_property', methods=['POST'])
def add_property():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    required_fields = ["owner_id", "property_type", "area", "city", "state", "country", 
                       "price", "contact_number", "email", "status", "name"]
    missing_fields = [field for field in required_fields if field not in data or not data[field]]

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()
        
        # Use the stored procedure to add a property
        property_id = None
        cursor.execute(
            "CALL add_property_proc(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                data['name'], data['owner_id'], data['property_type'], data['area'], 
                data.get('parking'), data['city'], data['state'], data['country'], 
                data['price'], data.get('balcony'), data.get('bedrooms'), 
                data['contact_number'], data['email'], data.get('description'), 
                data['status'], property_id
            )
        )
        
        # Get the returned property_id
        property_id = cursor.fetchone()[0] if cursor.description else None
        
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Property added successfully", "property_id": property_id}), 201
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_property/<int:property_id>', methods=['GET'])
def get_property(property_id):
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM properties WHERE property_id = %s", (property_id,))
        property_data = cursor.fetchone()
        
        if property_data is None:
            conn.close()
            return jsonify({"error": "Property not found"}), 404

        conn.close()
        return jsonify(dict(property_data)), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_favorite', methods=['POST'])
def add_favorite():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400

    required_fields = ["user_id", "property_id"]
    missing_fields = [field for field in required_fields if not data.get(field)]

    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    try:
        conn = db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (data["user_id"],))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "User not found"}), 404

        cursor.execute("SELECT 1 FROM properties WHERE property_id = %s", (data["property_id"],))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({"error": "Property not found"}), 404

        cursor.execute("INSERT INTO favorites (user_id, property_id) VALUES (%s, %s)",
                       (data["user_id"], data["property_id"]))

        conn.commit()
        conn.close()
        
        return jsonify({"message": "Property added to favorites"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Property already in favorites"}), 409
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

# New endpoint to view logs
@app.route('/operation_logs', methods=['GET'])
def get_operation_logs():
    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Optional filters
        table_name = request.args.get('table_name')
        operation_type = request.args.get('operation_type')
        
        query = "SELECT * FROM operation_logs"
        params = []
        where_clauses = []
        
        if table_name:
            where_clauses.append("table_name = %s")
            params.append(table_name)
            
        if operation_type:
            where_clauses.append("operation_type = %s")
            params.append(operation_type)
            
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        query += " ORDER BY operation_timestamp DESC"
        
        cursor.execute(query, params)
        logs = cursor.fetchall()
        conn.close()
        
        return jsonify([dict(log) for log in logs]), 200
    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # For Render, get port from environment
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
