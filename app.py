from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
# 配置 secret_key 用于 session
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')
# --- 数据库配置 ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 数据库模型 ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(80), nullable=False)
    bio = db.Column(db.Text)
    email = db.Column(db.String(120))
    registerDate = db.Column(db.String(20))
    avatar = db.Column(db.String(255))
    # 关系：一个用户可以有多篇文章
    posts = db.relationship('Post', backref='author_rel', lazy=True)
    # 关系：一个用户可以有多个视频
    videos = db.relationship('Video', backref='author_rel', lazy=True)
    # 关系：一个用户可以有多个订单
    orders = db.relationship('Order', backref='user_rel', lazy=True)

class Post(db.Model):
    __tablename__ = 'posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.Text)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    tags = db.Column(db.String(200))  # 以逗号分隔存储
    publishDate = db.Column(db.String(20))
    readTime = db.Column(db.String(20))
    views = db.Column(db.Integer, default=0)
    # 外键关联
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class Video(db.Model):
    __tablename__ = 'videos'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.String(500), nullable=False)
    duration = db.Column(db.String(20))
    uploadDate = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class Product(db.Model):
    """商品表"""
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.String(255))

class Order(db.Model):
    """订单主表"""
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # 允许匿名下单(虽然不推荐)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, paid, completed, cancelled
    create_time = db.Column(db.String(20))
    # 关系：一个订单包含多个明细
    items = db.relationship('OrderItem', backref='order_rel', lazy=True)

class OrderItem(db.Model):
    """订单明细表"""
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price_at_purchase = db.Column(db.Float, nullable=False) # 记录下单时的价格，防止商品调价影响历史订单

# 创建数据库表
with app.app_context():
    db.create_all()

@app.route('/')
def indexPage():
    """首页 - 展示文章列表"""
    posts = Post.query.all()
    return render_template('indexPage.html', posts=posts)

@app.route('/post/<int:postId>')
def postDetail(postId):
    """文章详情页"""
    post = Post.query.get(postId)
    if post is None:
        return render_template('errorPage.html', message='文章不存在'), 404
    
    # 激活阅读量统计：每次访问自增 1
    post.views += 1
    db.session.commit()
    
    # 判定当前用户是否为作者
    is_author = False
    if session.get('logged_in') and session.get('user_id') == post.user_id:
        is_author = True
    
    return render_template('postDetail.html', post=post, is_author=is_author)

@app.route('/about')
def aboutPage():
    """关于页面"""
    return render_template('aboutPage.html')

@app.route('/videos')
def videoPage():
    """播客视频展示页"""
    videos = Video.query.all()
    return render_template('videoPage.html', videos=videos)
    
@app.route('/shop')
def shopPage():
    """小店铺 - 商品橱窗"""
    products = Product.query.all()
    # 转换为模板需要的格式（ price 加上 ￥ 符号）
    formatted_products = []
    for p in products:
        formatted_products.append({
            'id': p.id,
            'name': p.name,
            'price': f"￥{p.price}",
            'description': p.description,
            'image': p.image
        })
    return render_template('shopPage.html', products=formatted_products)

@app.route('/cart')
def view_cart():
    """购物车页面"""
    cart_ids = session.get('cart', [])
    if not cart_ids:
        return render_template('cartPage.html', cart_items=[])
    
    # 统计每个商品出现的次数（数量）
    item_counts = {}
    for pid in cart_ids:
        item_counts[pid] = item_counts.get(pid, 0) + 1
    
    # 获取商品详情并组装列表
    items = []
    total_price = 0
    for pid, quantity in item_counts.items():
        product = Product.query.get(pid)
        if product:
            subtotal = product.price * quantity
            total_price += subtotal
            items.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'image': product.image,
                'quantity': quantity,
                'item_total': subtotal
            })
    
    return render_template('cartPage.html', items=items, total_price=total_price)



@app.route('/upload_video', methods=['GET', 'POST'])
def upload_video():
    """发布视频页面"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        duration = request.form.get('duration')
        file = request.files.get('video_file')

        if not title or not file:
            flash('标题和视频文件不能为空', 'error')
            return redirect(url_for('upload_video'))

        # 保存视频文件
        filename = secure_filename(file.filename)
        upload_folder = 'static/uploads/videos'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        from datetime import datetime
        new_video = Video(
            title=title,
            description=description,
            url=f'/static/uploads/videos/{filename}',
            duration=duration,
            uploadDate=datetime.now().strftime('%Y-%m-%d'),
            user_id=session.get('user_id')
        )

        try:
            db.session.add(new_video)
            db.session.commit()
            flash('视频发布成功！', 'success')
            return redirect(url_for('videoPage'))
        except Exception as e:
            db.session.rollback()
            flash('发布失败，请稍后再试', 'error')
            return redirect(url_for('upload_video'))

    return render_template('createVideo.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('请填写所有字段', 'error')
            return redirect(url_for('register'))
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
            return redirect(url_for('register'))
        
        # 创建真实用户对象，对密码进行哈希加密
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            nickname=username,
            bio='新加入的博主',
            email='',
            registerDate='2024-05-20',
            avatar=f'https://api.dicebear.com/7.x/avataaars/svg?seed={username}'
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功！请登录您的账号', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('服务器内部错误，请稍后再试', 'error')
            return redirect(url_for('register'))
            
    return render_template('registerPage.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('loginPage.html', error='请填写所有字段')
        
        # 从数据库查询真实用户对象
        user = User.query.filter_by(username=username).first()
        
        # 校验用户是否存在且密码正确
        if not user or not check_password_hash(user.password_hash, password):
            return render_template('loginPage.html', error='用户名或密码错误')
        
        # 存储用户 ID 到 session，提高稳定性
        session['user_id'] = user.id
        session['logged_in'] = True
        flash('登录成功！欢迎回来', 'success')
        return redirect(url_for('indexPage'))
    
    return render_template('loginPage.html')

@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('indexPage'))

@app.route('/profile')
def profile():
    """个人中心"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return render_template('errorPage.html', message='用户不存在'), 404
    
    # 将数据库模型转换为字典，以兼容现有的 profilePage.html 模板
    user_dict = {
        'username': user.username,
        'nickname': user.nickname,
        'bio': user.bio,
        'email': user.email,
        'registerDate': user.registerDate,
        'avatar': user.avatar
    }
    
    # 分页逻辑：获取当前页码，默认第 1 页，每页 6 篇文章
    page = request.args.get('page', 1, type=int)
    posts_pagination = Post.query.filter_by(user_id=user.id).order_by(Post.publishDate.desc()).paginate(page=page, per_page=6, error_out=False)
    
    # 获取文章总数用于侧边栏统计
    total_posts = Post.query.filter_by(user_id=user.id).count()
    
    return render_template('profilePage.html', user=user_dict, posts=posts_pagination, total_posts=total_posts)


@app.route('/profile/edit', methods=['GET', 'POST'])
def edit_profile():
    """编辑个人资料"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return render_template('errorPage.html', message='用户不存在'), 404

    if request.method == 'POST':
        nickname = request.form.get('nickname')
        bio = request.form.get('bio')
        if nickname and bio:
            user.nickname = nickname
            user.bio = bio
            db.session.commit()
            return redirect(url_for('profile'))
        return render_template('profilePage.html', user=user, error='请填写完整信息', edit_mode=True)
    
    # 转换为字典以兼容模板
    user_dict = {
        'username': user.username,
        'nickname': user.nickname,
        'bio': user.bio,
        'email': user.email,
        'registerDate': user.registerDate,
        'avatar': user.avatar
    }
    return render_template('profilePage.html', user=user_dict, edit_mode=True)

@app.route('/delete_post/<int:postId>')
def delete_post(postId):
    """删除文章"""
    if not session.get('logged_in'):
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    post = Post.query.get(postId)
    if post is None:
        flash('文章不存在', 'error')
        return redirect(url_for('indexPage'))
    
    # 权限校验：必须是作者才能删除
    if post.user_id != session.get('user_id'):
        flash('您没有权限删除这篇文章', 'error')
        return redirect(url_for('postDetail', postId=postId))
    
    try:
        db.session.delete(post)
        db.session.commit()
        flash('文章已成功删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败，请稍后再试', 'error')
    
    return redirect(url_for('indexPage'))

@app.route('/delete_video/<int:videoId>')
def delete_video(videoId):
    """删除视频"""
    if not session.get('logged_in'):
        flash('请先登录', 'error')
        return redirect(url_for('login'))
    
    video = Video.query.get(videoId)
    if video is None:
        flash('视频不存在', 'error')
        return redirect(url_for('videoPage'))
    
    # 权限校验：必须是作者才能删除
    if video.user_id != session.get('user_id'):
        flash('您没有权限删除这个视频', 'error')
        return redirect(url_for('videoPage'))
    
    try:
        # 物理文件删除：将 URL 转换为本地路径
        # url 格式为 /static/uploads/videos/filename
        relative_path = video.url.lstrip('/')
        if os.path.exists(relative_path):
            os.remove(relative_path)
            
        db.session.delete(video)
        db.session.commit()
        flash('视频已成功删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash('删除失败，请稍后再试', 'error')
    
    return redirect(url_for('videoPage'))

@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    """创建新文章页面"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        summary = request.form.get('summary')
        content = request.form.get('content')
        category = request.form.get('category')
        tags = request.form.get('tags')
        
        if not title or not content:
            flash('标题和正文不能为空', 'error')
            return redirect(url_for('create_post'))
        
        from datetime import datetime
        # 简单估算阅读时间：每 500 字 1 分钟
        read_time_val = f"{max(1, len(content) // 500)} 分钟"
        
        new_post = Post(
            title=title,
            summary=summary,
            content=content,
            category=category,
            tags=tags,
            publishDate=datetime.now().strftime('%Y-%m-%d'),
            readTime=read_time_val,
            user_id=session.get('user_id')
        )
        
        try:
            db.session.add(new_post)
            db.session.commit()
            flash('文章创建成功！', 'success')
            return redirect(url_for('indexPage'))
        except Exception as e:
            db.session.rollback()
            flash(f'创建失败: {str(e)}', 'error')
            return redirect(url_for('create_post'))

    return render_template('createPost.html')

@app.route('/create_product', methods=['GET', 'POST'])
def create_product():
    """创建新产品页面"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        file = request.files.get('product_image')

        if not name or not price or not file:
            flash('名称、价格和图片不能为空', 'error')
            return redirect(url_for('create_product'))

        # 保存图片文件
        filename = secure_filename(file.filename)
        upload_folder = 'static/uploads/products'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        try:
            new_product = Product(
                name=name,
                price=float(price),
                description=description,
                image=f'/static/uploads/products/{filename}'
            )
            db.session.add(new_product)
            db.session.commit()
            flash('产品上传成功！', 'success')
            return redirect(url_for('shopPage'))
        except Exception as e:
            db.session.rollback()
            flash('上传失败，请检查价格格式或稍后再试', 'error')
            return redirect(url_for('create_product'))

    return render_template('createProduct.html')


@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    """将商品添加到购物车"""
    data = request.get_json()
    product_id = data.get('productId')
    
    if not product_id:
        return jsonify({'success': False, 'message': '商品ID缺失'}), 400
    
    # 初始化购物车 session
    if 'cart' not in session:
        session['cart'] = []
    
    # 将商品ID添加到购物车（允许重复，代表数量增加）
    cart = session['cart']
    cart.append(product_id)
    session['cart'] = cart # 显式更新 session 以触发保存
    
    return jsonify({
        'success': True, 
        'cart_count': len(session['cart'])
    })

@app.route('/cart/remove', methods=['POST'])
def remove_from_cart():
    """从购物车中移除商品"""
    data = request.get_json()
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': '商品ID缺失'}), 400
    
    if 'cart' not in session:
        return jsonify({'success': False, 'message': '购物车为空'}), 400
    
    # 移除所有匹配该 product_id 的项（彻底移除该商品）
    cart = session.get('cart', [])
    updated_cart = [pid for pid in cart if pid != product_id]
    
    session['cart'] = updated_cart
    
    return jsonify({
        'success': True,
        'cart_count': len(updated_cart)
    })


if __name__ == '__main__':
    app.run(debug=True)

