from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Database Initialization
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            image TEXT NOT NULL,
            seller_id TEXT,
            CHECK (category IN ('electronics', 'fashion', 'furniture'))
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Processing',
            seller_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sellers (
            seller_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            business_name TEXT NOT NULL,
            business_address TEXT NOT NULL
        )
    ''')
    
    # For existing tables, check and add missing columns
    try:
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'seller_id' not in columns:
            cursor.execute('ALTER TABLE products ADD COLUMN seller_id TEXT')
    except sqlite3.Error as e:
        print(f"Error checking products table: {e}")
    
    try:
        cursor.execute("PRAGMA table_info(orders)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'seller_id' not in columns:
            cursor.execute('ALTER TABLE orders ADD COLUMN seller_id TEXT')
    except sqlite3.Error as e:
        print(f"Error checking orders table: {e}")
    
    conn.commit()
    conn.close()

init_db()

@app.context_processor
def utility_processor():
    def get_image_url(image_name, category):
        """Returns correct image URL whether local or placeholder"""
        static_path = os.path.join(app.static_folder, 'images', image_name)
        if os.path.exists(static_path):
            return url_for('static', filename=f'images/{image_name}')
        return f'https://source.unsplash.com/400x300/?{category}'
    return dict(get_image_url=get_image_url)

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    user_id = request.form['user_id']
    password = request.form['password']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[0], password):
        session['user_id'] = user_id
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    user_id = request.form['user_id']
    name = request.form['name']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    if password != confirm_password:
        flash("Passwords do not match", "error")
        return redirect(url_for('register'))

    hashed_password = generate_password_hash(password)

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, name, password) VALUES (?, ?, ?)",
            (user_id, name, hashed_password)
        )
        conn.commit()
        conn.close()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for('login'))
    except sqlite3.IntegrityError:
        flash("User ID already exists", "error")
        return redirect(url_for('register'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# Product Routes
@app.route('/')
def home():
    return render_template('home_page.html')

@app.route('/products')
def products():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM users WHERE user_id = ?", (session['user_id'],))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return redirect(url_for('login'))
    
    user_name = user[0]
    
    cursor.execute("SELECT * FROM products ORDER BY category, name")
    products = cursor.fetchall()
    conn.close()
    
    products_list = []
    for p in products:
        products_list.append({
            'product_id': p[0], 
            'name': p[1], 
            'price': p[2], 
            'category': p[3],
            'image': p[4]
        })
    
    products_by_category = {}
    for product in products_list:
        products_by_category.setdefault(product['category'], []).append(product)
    
    return render_template('products.html', 
                         user_name=user_name, 
                         products_by_category=products_by_category)

# Buy Now Route (added to fix the BuildError)
@app.route('/buy_now', methods=['POST'])
def buy_now():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    product_id = request.form.get('product_id')
    if not product_id:
        flash('Invalid product', 'error')
        return redirect(url_for('products'))
    
    # Add directly to cart and proceed to checkout
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Clear existing cart items
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
    
    # Add the single product to cart
    cursor.execute('''
        INSERT INTO cart (user_id, product_id, quantity)
        VALUES (?, ?, ?)
    ''', (session['user_id'], product_id, 1))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('checkout'))

# Cart Routes
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    product_id = request.form.get('product_id')
    if not product_id:
        flash('Invalid product', 'error')
        return redirect(url_for('products'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Check if product already in cart
    cursor.execute('''
        SELECT quantity FROM cart 
        WHERE user_id = ? AND product_id = ?
    ''', (session['user_id'], product_id))
    
    item = cursor.fetchone()
    
    if item:
        # Update quantity if already in cart
        new_quantity = item[0] + 1
        cursor.execute('''
            UPDATE cart SET quantity = ?
            WHERE user_id = ? AND product_id = ?
        ''', (new_quantity, session['user_id'], product_id))
    else:
        # Add new item to cart
        cursor.execute('''
            INSERT INTO cart (user_id, product_id)
            VALUES (?, ?)
        ''', (session['user_id'], product_id))
    
    conn.commit()
    conn.close()
    flash('Product added to cart', 'success')
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM cart 
        WHERE cart_id = ? AND user_id = ?
    ''', (cart_id, session['user_id']))
    
    conn.commit()
    conn.close()
    flash('Item removed from cart', 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.cart_id, p.product_id, p.name, p.price, p.image, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
    ''', (session['user_id'],))
    
    cart_items = cursor.fetchall()
    
    total = sum(item[3] * item[5] for item in cart_items)
    
    conn.close()
    return render_template('mycart.html', cart_items=cart_items, total=total)


# Order Routes
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.product_id, c.quantity, p.seller_id, p.price
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
    ''', (session['user_id'],))
    
    cart_items = cursor.fetchall()
    
    for product_id, quantity, seller_id, price in cart_items:
        total_price = price * quantity
        cursor.execute('''
            INSERT INTO orders (user_id, product_id, quantity, total_price, seller_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], product_id, quantity, total_price, seller_id))
    
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()
    
    flash('Order placed successfully!', 'success')
    return redirect(url_for('view_orders'))



# Add Product (Seller)
@app.route('/seller/add_product', methods=['GET', 'POST'])
def add_product():
    if 'seller_id' not in session:
        return redirect(url_for('seller_login'))
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        category = request.form['category']
        image = request.files['image']
        
        # Save image
        if image:
            filename = f"{name.replace(' ', '_').lower()}.jpg"
            image.save(os.path.join(app.static_folder, 'images', filename))
        else:
            filename = 'default-product.jpg'
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (name, price, category, image, seller_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, price, category, filename, session['seller_id']))
        conn.commit()
        conn.close()
        
        flash('Product added successfully!', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html')
# Seller Registration
@app.route('/seller/register', methods=['GET', 'POST'])
def seller_register():
    if request.method == 'GET':
        return render_template('seller_register.html')
    
    seller_id = request.form['seller_id']
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    business_name = request.form['business_name']
    business_address = request.form['business_address']
    
    hashed_password = generate_password_hash(password)
    
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sellers (seller_id, name, email, password, business_name, business_address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (seller_id, name, email, hashed_password, business_name, business_address))
        conn.commit()
        conn.close()
        flash('Seller registration successful! Please login.', 'success')
        return redirect(url_for('seller_login'))
    except sqlite3.IntegrityError:
        flash('Seller ID or Email already exists', 'error')
        return redirect(url_for('seller_register'))

# Seller Login
@app.route('/seller/login', methods=['GET', 'POST'])
def seller_login():
    if request.method == 'GET':
        return render_template('seller_login.html')
    
    seller_id = request.form['seller_id']
    password = request.form['password']

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM sellers WHERE seller_id = ?", (seller_id,))
    seller = cursor.fetchone()
    conn.close()

    if seller and check_password_hash(seller[0], password):
        session['seller_id'] = seller_id
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401



# Seller Logout
@app.route('/seller/logout')
def seller_logout():
    session.pop('seller_id', None)
    return redirect(url_for('home'))


# Seller Dashboard
@app.route('/seller/dashboard')
def seller_dashboard():
    if 'seller_id' not in session:
        return redirect(url_for('seller_login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Get seller's products
    cursor.execute('''
        SELECT * FROM products 
        WHERE seller_id = ?
        ORDER BY product_id DESC
    ''', (session['seller_id'],))
    products = cursor.fetchall()
    
    # Get seller's orders
    cursor.execute('''
        SELECT o.order_id, p.name, p.price, o.quantity, o.total_price, 
               u.name as buyer_name, o.order_date, o.status
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        JOIN users u ON o.user_id = u.user_id
        WHERE p.seller_id = ?
        ORDER BY o.order_date DESC
    ''', (session['seller_id'],))
    orders = cursor.fetchall()
    
    conn.close()
    
    return render_template('seller_dashboard.html', products=products, orders=orders)


# Add this route to handle GET requests for checkout page
@app.route('/checkout', methods=['GET'])
def checkout_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.cart_id, p.product_id, p.name, p.price, p.image, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
    ''', (session['user_id'],))
    
    cart_items = cursor.fetchall()
    total = sum(item[3] * item[5] for item in cart_items)
    
    conn.close()
    
    if not cart_items:
        flash('Your cart is empty', 'error')
        return redirect(url_for('view_cart'))
    
    return render_template('checkout.html', cart_items=cart_items, total=total)



@app.route('/orders')
def view_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.order_id, p.product_id, p.name, p.price, p.image, o.quantity, 
               o.total_price, o.order_date, o.status
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        WHERE o.user_id = ?
        ORDER BY o.order_date DESC
    ''', (session['user_id'],))
    
    orders = cursor.fetchall()
    conn.close()
    
    return render_template('vieworder.html', orders=orders)

# Static files route
@app.route('/static/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'), filename)

if __name__ == '__main__':
    os.makedirs(os.path.join(app.static_folder, 'images'), exist_ok=True)
    app.run(debug=True)