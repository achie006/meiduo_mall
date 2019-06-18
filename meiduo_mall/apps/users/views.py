import json
import re
# from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django import http
from django.utils.decorators import method_decorator
from django.views import View
from django_redis import get_redis_connection
import logging
from celery_tasks.email.tasks import send_email_verify
from goods.models import SKU
from meiduo_mall.utils.views import LoginRequiredView
from .utils import generate_email_verify_url, check_verify_token
from meiduo_mall.utils.response_code import RETCODE
from .models import User, Address as Addresses
from django.contrib.auth import login, authenticate, logout, mixins
from django.conf import settings
from carts.utils import merge_cart_cookie_to_redis
logger = logging.getLogger('django')


# Create your views here.


class RegisterView(View):
    """用户注册"""

    def get(self, request):
        """
            提供注册界面
            :param request: 请求对象
            :return: 注册界面
        """
        return render(request, 'register.html')

    def post(self, request):
        """
        实现用户注册
        :param request: 请求对象
        :return: 注册结果
        """
        # 1.接受数据
        query_dict = request.POST
        username = query_dict.get('username')
        password = query_dict.get('password')
        password2 = query_dict.get('password2')
        mobile = query_dict.get('mobile')
        sms_code = query_dict.get('sms_code')
        allow = query_dict.get('allow')

        # 2.校验数据
        # 判断接受到的数据是否齐全
        if all([username, password, password2, mobile, sms_code, allow]) is False:
            return http.HttpResponseForbidden('缺少必要参数')

        # 判断每项数据是否有效
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入5-20个字符的用户名')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')
        if password != password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('您输入的手机号格式不正确')
        # 短信验证码后期在补充逻辑
        # 2.1 连接数据库
        redis_conn = get_redis_connection('verify_code')
        # 2.2 获取短信验证码并删除验证码保证验证码只能使用一次
        sms_code_server = redis_conn.get('sms_code_%s' % mobile)
        # redis_conn.delete('sms_%s' % mobile)
        # 2.3 判断验证码是否过期
        if sms_code_server is None:
            return http.HttpResponseForbidden('短信验证码已过期')
        redis_conn.delete('sms_code_%s' % mobile)
        # 2.4 判断验证码是否正确
        # redis数据库中是bytes类型，需要解码
        sms_code_server = sms_code_server.decode()
        if sms_code != sms_code_server:
            return http.HttpResponseForbidden('请输入正确的短信验证码')

        # 3.保存或者处理数据
        user = User.objects.create_user(username=username, password=password, mobile=mobile)

        login(request, user)
        response = redirect('/')
        # 向cookie中保存username
        response.set_cookie("username", username, max_age=3600)

        # 4.响应请求

        return response


class UsernameCountView(View):
    """判断还用户名是否注册"""

    def get(self, request, username):
        # 获取当前数据库里面的数量值可能是0或者1
        count = User.objects.filter(username=username).count()
        if count != 0:
            return http.HttpResponseForbidden('用户名已存在')
        response_data = {'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'}
        return http.JsonResponse(response_data)


class MobileCountView(View):
    """判断手机号是否注册"""

    def get(self, request, mobile):
        count = User.objects.filter(mobile=mobile).count()
        if count != 0:
            return http.HttpResponseForbidden('手机号已存在')
        response_data = {'count': count, 'code': RETCODE.OK, 'errmsg': 'OK'}
        return http.JsonResponse(response_data)


class LoginView(View):
    """用户登录"""

    def get(self, request):
        """展示登陆界面"""
        return render(request, 'login.html')

    def post(self, request):
        """用户登录逻辑"""
        # 1.接受数据
        username = request.POST.get('username')
        password = request.POST.get('password')
        remembered = request.POST.get('remembered')

        # 多账号登陆偷懒版
        # if re.match(r'^1[3-9]\d{9}$', username):
        #     User.USERNAME_FIELD = 'mobile'

        user = authenticate(request, username=username, password=password)
        # 2.校验
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})
        # 在使用完手机登陆后在将用户改回来
        # User.USERNAME_FIELD = 'username'
        # 3.保存状态
        login(request, user)
        # 如何记录是否保持登陆
        if remembered == 'on':
            request.session.set_expiry(0)
        # 4.响应：重定向到首页
        next = request.GET.get('next')
        response = redirect(next or '/')
        # 前端使用vueif来判断cookie中username有值否
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE if remembered else None)
        # SESSION_COOKIE_AGE在全剧配置文件里

        # 在此处合并购物车
        merge_cart_cookie_to_redis(request, response)
        return response


class LogoutView(View):
    """用户退出登陆"""

    def get(self, request):
        # 1.清除状态操持信息，django中自带的logout方法
        logout(request)
        # 2.创建重定向对象，重定向到登陆页面
        response = redirect('/login/')
        # 3.清除cookie中的username信息
        response.delete_cookie('username')

        return response


class UserInfoView(mixins.LoginRequiredMixin, View):
    """用户中心界面"""

    # def get(self, request):
    # is_authenticated判断user是否存在
    # user = request.user
    # # 判断用户是否真实存在
    # if user.is_authenticated:
    #     return render(request, 'user_center_info.html')
    # else:
    #     return redirect('/login/?next=/info/')

    # 使用类试图的装饰器方法
    # @method_decorator(login_required)
    # def get(self, request):
    #
    #     return render(request, 'user_center_info.html')

    # 使用扩展类的方法
    def get(self, request):
        return render(request, 'user_center_info.html')


class EmailView(mixins.LoginRequiredMixin, View):
    """设置用户邮箱"""

    def put(self, request):
        """实现邮箱逻辑"""
        # 1.接受json数据
        json_dict = json.loads(request.body.decode())
        email = json_dict.get('email')

        # 2.校验数据
        if not email:
            return http.JsonResponse({'code': RETCODE.NECESSARYPARAMERR, 'errmsg': '缺少必传参数'})
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return http.JsonResponse({'code': RETCODE.EMAILERR, 'errmsg': '请输入正确邮箱'})

        # 3.赋值email字段
        # 普通方法保存email
        user = request.user
        # user.email = email
        # user.save()
        # 乐观锁
        User.objects.filter(username=user.username, email='').update(email=email)

        # 设置完email以后该发送激活码给email
        # send_mail(subject, message, from_email, recipient_list,html_message=None)
        # 获取路由
        verify_url = generate_email_verify_url(user)
        send_email_verify.delay(email, verify_url)
        # 4，响应json数据
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加邮箱成功'})


class VerifyEmailView(View):
    """激活邮箱"""

    def get(self, request):
        # 接受token参数
        token = request.GET.get('token')
        # 校验
        if token is None:
            return http.HttpResponseForbidden('缺少token')
        # 对token进行解密获取user
        user = check_verify_token(token)
        if user is None:
            return http.HttpResponseForbidden('token无效')
        # 修改user指定的email_active字段
        user.email_active = True
        user.save()
        # 激活成功到用户中心
        return redirect('/info/')


class AddressView(LoginRequiredView):
    """用户收获地址"""

    def get(self, request):
        """用户收货地址展示"""
        user = request.user
        # 查询当前用户的所有地址
        address_qs = Addresses.objects.filter(user=user, is_deleted=False)
        if len(address_qs) == 0:
            return render(request, 'user_center_site.html')
        # 定义一个列表变量用来包装所有的的收货地址字典数据
        address_list1 = []

        for address_model in address_qs:
            dict = {
                'id': address_model.id,
                'title': address_model.title,
                "receiver": address_model.receiver,
                "province": address_model.province.name,
                "province_id": address_model.province.id,
                "city": address_model.city.name,
                "city_id": address_model.city.id,
                "district": address_model.district.name,
                "district_id": address_model.district.id,
                "place": address_model.place,
                "mobile": address_model.mobile,
                "tel": address_model.tel,
                "email": address_model.email
            }
            address_list1.append(dict)
        # 准备渲染数据
        context = {
            'addresses': address_list1,
            'default_address_id': user.default_address_id
        }
        return render(request, 'user_center_site.html', context)


class CreateAddressView(LoginRequiredView):
    """收货地址新增"""

    def post(self, request):
        # 判断用户的收货地址是否上线
        user = request.user
        # count = user.address.filter(is_deleted=False).count()
        count = Addresses.objects.filter(user=user, is_deleted=False).count()
        if count > 20:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '收货地址超过上限'})
        # 接受请求体数据

        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')
        # 校验
        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')
        # 保存收货地址数据
        try:
            address_model = Addresses.objects.create(
                user=request.user,
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
            # 如果当前用户还没有默认收货地址,就把当前新增的这个收货地址设置为它的默认地址
            if not user.default_address:
                user.default_address = address_model
                user.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '新增收货地址失败'})

        # 把保存好的模型对象转换成字段，再响应给前端
        address_dict = {
            'id': address_model.id,
            'title': address_model.title,
            "receiver": address_model.receiver,
            "province": address_model.province.name,
            "province_id": address_model.province.id,
            "city": address_model.city.name,
            "city_id": address_model.city.id,
            "district": address_model.district.name,
            "district_id": address_model.district.id,
            "place": address_model.place,
            "mobile": address_model.mobile,
            "tel": address_model.tel,
            "email": address_model.email
        }
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '新增地址成功', 'address': address_dict})


class UpdateDestroyAddressView(LoginRequiredView):
    """修改和删除用户收货地址"""

    def put(self, request, address_id):
        """修改地址"""
        # 接受请求体数据
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验
        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 修改收货地址数据
        try:
            Addresses.objects.filter(id=address_id).update(
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '修改收货地址失败'})
        # 获取到修改后的地址模型对象
        address_model = Addresses.objects.get(id=address_id)
        address_dict = {
            'id': address_model.id,
            'title': address_model.title,
            "receiver": address_model.receiver,
            "province": address_model.province.name,
            "province_id": address_model.province.id,
            "city": address_model.city.name,
            "city_id": address_model.city.id,
            "district": address_model.district.name,
            "district_id": address_model.district.id,
            "place": address_model.place,
            "mobile": address_model.mobile,
            "tel": address_model.tel,
            "email": address_model.email
        }
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'ok', 'address': address_dict})

    def delete(self, request, address_id):
        """删除地址"""
        try:
            address = Addresses.objects.filter(id=address_id)
            address.is_deleted = True
            address.save()
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除地址成功'})
        except Addresses.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '地址不存在'})


class DefaultAddressView(LoginRequiredView):
    """设置默认收货地址"""

    def put(self, request, address_id):
        # 查询指定id的收货地址
        try:
            address = Addresses.objects.get(id=address_id)
            user = request.user
            # 把指定的收货地址设置给user的default——address字段
            user.default_address = address
            user.save()
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '设置默认地址成功'})
        except Addresses.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '设置默认地址失败'})


class UpdateTitleAddressView(LoginRequiredView):
    """修改用户收货地址标题"""

    def put(self, request, address_id):
        # 接受请求体中的地址标题
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')

        # 校验
        if title is None:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '缺少必传参数'})

        # 把要修改的收货地质获取
        try:
            address = Addresses.objects.get(id=address_id)
            # 修改地址的标题
            address.title = title
            address.save()

            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改标题成功'})
        except Addresses.DoesNotExist:
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '修改标题失败'})


class ChangePasswordView(LoginRequiredView):
    """修改用户密码"""

    def get(self, request):
        """展示页面"""
        return render(request, 'user_center_pass.html')

    def post(self, request):
        """修改密码逻辑"""
        # 接受请求体中的表单数据
        query_dict = request.POST
        old_password = query_dict.get('old_pwd')
        new_password = query_dict.get('new_pwd')
        new_password2 = query_dict.get('new_cpwd')

        # 校验
        if all([old_password, new_password, new_password2]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        # 获取当前登陆用户
        user = request.user
        if user.check_password(old_password) is False:
            return render(request, 'user_center_pass.html', {'old_password_errmsg': '原密码错误'})
        if re.match(r'^[0-9A-Za-z]{8,20}$', new_password) is False:
            return http.HttpResponseForbidden('密码最少8位，最长20位')
        if new_password != new_password2:
            return http.HttpResponseForbidden('两次密码不一致')
        # 修改用户密码set_password方法
        user.set_password(new_password)
        user.save()
        # 清除状态保持
        logout(request)
        # 清除cookie中的username
        response = redirect('/login/')
        response.delete_cookie('username')
        # 重定向到login界面
        return response


class UserBrowseHistory(LoginRequiredView):
    """商品浏览记录"""

    def post(self, request):
        """保存浏览记录逻辑"""
        # 1.接受请求体中的sku_id
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')

        try:
            # 2.校验sku_id的真实有效性
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')

        # 创建redis连接对象
        redis_conn = get_redis_connection('history')
        pl = redis_conn.pipeline()
        # 获取当前用户
        user = request.user
        # 拼接用户list的key
        key = 'history_%s' % user.id
        # 先去重
        pl.lrem(key, 0, sku_id)
        # 添加到列表开头
        pl.lpush(key, sku_id)
        # 截取列表中前五个元素
        pl.ltrim(key, 0, 4)
        # 执行管道
        pl.execute()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})

    def get(self, request):
        """获取用户浏览器记录逻辑"""
        # 1. 获取当前的登陆用户对象
        user = request.user
        # 2. 创建redis连接对象
        redis_conn = get_redis_connection('history')
        # 获取当前用户在redis中的所有浏览记录列表
        sku_ids = redis_conn.lrange('history_%s' % user.id, 0, -1)
        # 创建一个保存sku字典的列表
        skus = []
        # 在通过列表中的sku_id获取到每一个sku模型
        for sku_id in sku_ids:
            # 在将sku模型转换成字典
            sku_model = SKU.objects.get(id=sku_id)
            skus.append({
                'id': sku_model.id,
                'name': sku_model.name,
                'default_image_url': sku_model.default_image.url,
                'price': sku_model.price,
            })
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'skus': skus})


class FindPasswordView(View):
    """召回密码"""
    def get(self, request):

        return render(request, 'find_password.html')

    def post(self, request):
        # 获取form表单中的数据
        qurey_dict = request.POST
        username = qurey_dict.get('username')

        # 校验
        # 处理数据
        # 响应
        pass


