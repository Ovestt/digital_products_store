from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'zip', 'pdf'}
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    products = db.relationship('Product', backref='creator', lazy=True)
    purchases = db.relationship('Purchase', back_populates='user', lazy=True)
    cart_items = db.relationship('Cart', back_populates='user', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    cover_image = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(200), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    purchases = db.relationship('Purchase', back_populates='product', lazy=True, cascade='all, delete-orphan')
    in_cart = db.relationship('Cart', back_populates='product', lazy=True)   

    def __repr__(self):
        return f'<Product {self.name}>'
class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product', back_populates='in_cart')
    user = db.relationship('User', back_populates='cart_items')

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    product = db.relationship('Product', back_populates='purchases')
    user = db.relationship('User', back_populates='purchases')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

with app.app_context():
    db.create_all()
    print("Все таблицы успешно созданы!")

# Главная страница
@app.route('/')
def index():
    # Получаем параметры фильтрации
    search_query = request.args.get('search', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    creator_filter = request.args.get('creator', '')
    page = request.args.get('page', 1, type=int)
    per_page = 64
    
    query = Product.query.join(User)
    
    # Применяем фильтры
    if search_query:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search_query}%'),
                Product.description.ilike(f'%{search_query}%')
            )
        )
    
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    
    if creator_filter:
        query = query.filter(User.username.ilike(f'%{creator_filter}%'))
    
    # Получаем товары с пагинацией
    products_pagination = query.order_by(Product.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    products = products_pagination.items
    
    # Получаем товары в корзине текущего пользователя (если он авторизован)
    current_user_cart = []
    if 'user_id' in session:
        cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
        current_user_cart = [item.product_id for item in cart_items]
    
    return render_template(
        'index.html', 
        products=products,
        current_user_cart=current_user_cart,
        pagination=products_pagination  # Передаем объект пагинации в шаблон
    )


# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Регистрация успешна. Пожалуйста залогиньтесь.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Логин
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль')
    
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Добавление товара
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        cover = request.files['cover']
        product_file = request.files['product_file']
        
        if not (cover and product_file and allowed_file(cover.filename) and allowed_file(product_file.filename)):
            flash('Неверный формат')
            return redirect(url_for('add_product'))
        
        cover_filename = f"cover_{session['user_id']}_{secure_filename(cover.filename)}"
        product_filename = f"product_{session['user_id']}_{secure_filename(product_file.filename)}"

        cover_path = os.path.join(app.config['UPLOAD_FOLDER'], cover_filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], product_filename)
        
        cover.save(cover_path)
        product_file.save(file_path)
        
        product = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            cover_image=cover_filename, 
            file_path=product_filename,
            creator_id=session['user_id']
        )
        db.session.add(product)
        db.session.commit()
        return redirect(url_for('index'))
    
    return render_template('add_product.html')

# Корзина
@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    products = [item.product for item in cart_items]
    total = sum(p.price for p in products)
    
    return render_template('cart.html', products=products, total=total)

# Добавить в корзину
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Проверяем, нет ли уже товара в корзине
    if not Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).first():
        cart_item = Cart(user_id=session['user_id'], product_id=product_id)
        db.session.add(cart_item)
        db.session.commit()
        flash('Товар добавлен в корзину')
    else:
        flash('Товар уже в корзине')
    
    return redirect(url_for('index'))

# Удалить из корзины
@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).delete()
    db.session.commit()
    return redirect(url_for('cart'))

# Покупка
@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    
    if not cart_items:
        flash('Ваша корзина пуста')
        return redirect(url_for('cart'))
    
    # Добавляем все товары в покупки
    for item in cart_items:
        purchase = Purchase(user_id=session['user_id'], product_id=item.product_id)
        db.session.add(purchase)
    
    # Очищаем корзину
    Cart.query.filter_by(user_id=session['user_id']).delete()
    db.session.commit()
    
    flash('Оплата прошла! Проверьте ваш профиль, чтобы скачать товар.')
    return redirect(url_for('profile'))

# Скачивание товара
@app.route('/download/<int:product_id>')
def download(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Проверяем, что товар куплен
    if not Purchase.query.filter_by(user_id=session['user_id'], product_id=product_id).first():
        flash('Вы не приобретали этот товар')
        return redirect(url_for('profile'))
    
    product = Product.query.get(product_id)
    return send_from_directory(
        os.path.dirname(product.file_path),
        os.path.basename(product.file_path),
        as_attachment=True
    )

# Профиль пользователя
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    purchases = Purchase.query.filter_by(user_id=session['user_id']).all()
    return render_template('profile.html', purchases=purchases)

# Продукты пользователя
@app.route('/my_products')
def my_products():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Получаем товары текущего пользователя
    products = Product.query.filter_by(creator_id=session['user_id']).all()
    return render_template('my_products.html', products=products)

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product = Product.query.get_or_404(product_id)
    
    # Проверяем, что товар принадлежит текущему пользователю
    if product.creator_id != session['user_id']:
        flash('You can only edit your own products', 'error')
        return redirect(url_for('my_products'))

    if request.method == 'POST':
        try:
            product.name = request.form['name']
            product.description = request.form['description']
            product.price = float(request.form['price'])
            
            # Обновляем обложку, если загружена новая
            if 'cover' in request.files:
                cover = request.files['cover']
                if cover.filename != '' and allowed_file(cover.filename):
                    # Удаляем старую обложку
                    if os.path.exists(product.cover_image):
                        os.remove(product.cover_image)
                    # Сохраняем новую
                    cover_path = os.path.join(app.config['UPLOAD_FOLDER'], f"cover_{session['user_id']}_{secure_filename(cover.filename)}")                    
                    cover.save(cover_path)
                    product.cover_image = cover_path
            
            db.session.commit()
            flash('Товар успешно обновлен', 'success')
            return redirect(url_for('my_products'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка обновления товара: {str(e)}', 'error')
    
    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    product = Product.query.get_or_404(product_id)
    
    if product.creator_id != session['user_id']:
        flash('Вы можете удалить только свои собственные товары', 'error')
        return redirect(url_for('my_products'))
    
    try:
        # Удаляем файлы товара
        if os.path.exists(product.cover_image):
            os.remove(product.cover_image)
        if os.path.exists(product.file_path):
            os.remove(product.file_path)
        
        db.session.delete(product)
        db.session.commit()
        flash('Товар успешно удалён', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка удаления товара: {str(e)}', 'error')
    
    return redirect(url_for('my_products'))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Проверяем, находится ли товар в корзине
    in_cart = False
    if 'user_id' in session:
        cart_item = Cart.query.filter_by(
            user_id=session['user_id'],
            product_id=product.id
        ).first()
        in_cart = cart_item is not None
    
    return render_template(
        'product_detail.html',
        product=product,
        in_cart=in_cart
    )
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)

