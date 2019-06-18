from django.conf.urls import url

from payment import views

urlpatterns = [
    # 发起支付
    url(r'^payment/(?P<order_id>\d+)/$', views.PaymentView.as_view()),
    # 支付成功后回调处理
    url(r'^payment/status/$', views.PaymentStatusView.as_view()),
]