from django.conf.urls import url
from orders import views

urlpatterns = [
    url(r'^orders/settlement/$', views.OrderSettlementView.as_view()),
    url(r'^orders/commit/$', views.OrderCommitView.as_view()),
    url(r'^orders/success/$', views.OrderSuccessView.as_view()),
    # url(r'^orders/comment/?order_id=(?P<order_id>\d+)/$', views.OrderGoodsView.as_view()),
    url(r'^orders/comment/$', views.OrderGoodsView.as_view()),
]