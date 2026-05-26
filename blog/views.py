from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.generic import FormView
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from taggit.models import Tag
import json
import random

from .models import *
from .forms import CreateUserForm, AccountForm


# ===============================
# SAFE CUSTOMER HANDLER
# ===============================
def get_customer(user):
    try:
        return user.customer
    except:
        return None


# ===============================
# HOME PAGE
# ===============================
def homePage(request, tag_slug=None):
    products = Product.objects.filter(status='published')

    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        products = Product.objects.filter(tags__in=[tag])

    order_items_count = 0

    if request.user.is_authenticated:
        customer = get_customer(request.user)
        if customer:
            order, created = Order.objects.get_or_create(customer=customer, complete=False)
            order_items_count = order.get_total_products

    paginator = Paginator(products, 8)
    page = request.GET.get('page')

    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)

    return render(request, 'blog/partials/content.html', {
        'products': products,
        'page': page,
        'order_items_count': order_items_count,
    })


# ===============================
# PRODUCT DETAIL
# ===============================
def productDetail(request, pk, slug):
    product = get_object_or_404(Product, id=pk, slug=slug, status='published')

    order_items_count = 0

    if request.user.is_authenticated:
        customer = get_customer(request.user)
        if customer:
            order, created = Order.objects.get_or_create(customer=customer, complete=False)
            order_items_count = order.get_total_products

    product_tags = product.tags.values_list('id', flat=True)

    similar_products = Product.objects.filter(
        tags__in=product_tags,
        status='published'
    ).exclude(id=product.id).annotate(
        same_tags=Count('tags')
    ).order_by('-same_tags', '-publish')[:4]

    return render(request, 'blog/partials/product_detail.html', {
        'product': product,
        'similar_products': similar_products,
        'order_items_count': order_items_count,
    })


# ===============================
# CART PAGE
# ===============================
def cart(request):
    if not request.user.is_authenticated:
        return redirect('blog:login')

    customer = get_customer(request.user)
    if not customer:
        return redirect('blog:login')

    order, created = Order.objects.get_or_create(customer=customer, complete=False)
    items = OrderItem.objects.filter(order=order)
    delivery = Delivery.objects.filter(active=True)

    if request.method == "POST":
        from django.utils import timezone

        now = timezone.now()
        code = request.POST.get('code')

        try:
            coupon = Coupon.objects.get(
                code__iexact=code,
                valid_from__lte=now,
                valid_to__gte=now,
                active=True
            )
            order.coupons = coupon
            order.save()
            messages.success(request, f"Discount applied: -${coupon.discount}")
        except:
            messages.info(request, "Invalid Coupon")

    return render(request, 'blog/partials/cart.html', {
        'items': items,
        'order': order,
        'delivery': delivery,
        'order_items_count': order.get_total_products,
    })


# ===============================
# CHECKOUT
# ===============================
def checkout(request):
    if not request.user.is_authenticated:
        return redirect('blog:login')

    customer = get_customer(request.user)
    if not customer:
        return redirect('blog:login')

    if not (customer.first_name and customer.last_name and customer.email and customer.phone and customer.address):
        messages.error(request, "Please complete your profile first")
        return redirect('blog:cart')

    order, created = Order.objects.get_or_create(customer=customer, complete=False)
    items = OrderItem.objects.filter(order=order)

    return render(request, 'blog/partials/checkout.html', {
        'items': items,
        'order': order,
        'customer': customer,
        'order_items_count': order.get_total_products,
    })


# ===============================
# UPDATE CART (AJAX)
# ===============================
def updateItem(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=403)

    customer = get_customer(request.user)
    if not customer:
        return JsonResponse({"error": "no customer"}, status=403)

    data = json.loads(request.body)
    productId = data['productId']
    action = data['action']

    product = get_object_or_404(Product, id=productId)
    order, created = Order.objects.get_or_create(customer=customer, complete=False)
    orderItem, created = OrderItem.objects.get_or_create(product=product, order=order)

    if action == "add":
        orderItem.quantity += 1

    elif action == "remove":
        orderItem.quantity -= 1

    elif action == "delete":
        orderItem.delete()
        return JsonResponse("deleted", safe=False)

    if orderItem.quantity <= 0:
        orderItem.delete()
    else:
        orderItem.save()

    return JsonResponse("updated", safe=False)


# ===============================
# REGISTER
# ===============================
class registerPage(FormView):
    template_name = 'blog/account/register.html'
    form_class = CreateUserForm
    success_url = reverse_lazy('blog:login')

    def form_valid(self, form):
        user = form.save()
        Customer.objects.create(user=user, email=form.cleaned_data['email'])
        return super().form_valid(form)


# ===============================
# LOGIN
# ===============================
class loginPage(LoginView):
    template_name = 'blog/account/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('blog:home')


# ===============================
# LOGOUT
# ===============================
@login_required
def logoutPage(request):
    logout(request)
    return redirect('blog:login')


# ===============================
# ACCOUNT PAGE
# ===============================
@login_required
def accountPage(request):
    customer = get_customer(request.user)
    if not customer:
        return redirect('blog:home')

    order_history = Order.objects.filter(customer=customer, complete=True)

    if request.method == "POST":
        form = AccountForm(request.POST, request.FILES)
        if form.is_valid():
            cd = form.cleaned_data

            customer.first_name = cd['first_name']
            customer.last_name = cd['last_name']
            customer.email = cd['email']
            customer.phone = cd['phone']
            customer.address = cd['address']

            if request.FILES.get('image'):
                customer.image = request.FILES['image']

            customer.save()
            return redirect('blog:account')
    else:
        form = AccountForm()

    return render(request, 'blog/account/account.html', {
        'customer': customer,
        'accForm': form,
        'order_history': order_history,
    })


# ===============================
# SEARCH
# ===============================
def post_search(request):
    query = request.GET.get('query')

    if query:
        lookup = Q(title__icontains=query) | Q(description__icontains=query) | Q(tags__name__icontains=query)
        products = Product.objects.filter(lookup, status='published')
    else:
        products = Product.objects.none()

    return render(request, 'blog/partials/content.html', {
        'products': products,
    })


# ===============================
# PAYMENT
# ===============================
@login_required
def payment(request):
    return render(request, 'blog/partials/payment.html')


# ===============================
# PAYMENT SUCCESS
# ===============================
@login_required
def payment_success(request):
    customer = get_customer(request.user)
    if not customer:
        return redirect('blog:login')

    order = Order.objects.get(customer=customer, complete=False)
    order.transaction_id = random.randint(10000, 100000)
    order.complete = True
    order.save()

    return redirect('blog:account')