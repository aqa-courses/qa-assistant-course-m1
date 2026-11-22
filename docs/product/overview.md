---
title: Обзор Shoplite
area: общее
updated: 2026-08-20
---

# Обзор Shoplite

Shoplite — интернет-магазин компьютерной периферии и аксессуаров. Покупатель входит в аккаунт, выбирает товары в каталоге, собирает корзину, применяет промокод и оформляет заказ с доставкой.

## Разделы

| Раздел | Адрес | Спецификация |
|---|---|---|
| Вход | `/login` | [login.md](login.md) |
| Каталог и поиск | `/catalog` | [catalog.md](catalog.md), [search.md](search.md), [filters-and-sorting.md](filters-and-sorting.md) |
| Карточка товара | `/product/{id}` | [product-page.md](product-page.md) |
| Корзина | `/cart` | [cart.md](cart.md), [cart-limits.md](cart-limits.md), [promo-codes.md](promo-codes.md), [shipping.md](shipping.md) |
| Оформление | `/checkout` | [checkout.md](checkout.md) |
| Заказы и профиль | `/orders/{id}`, `/profile` | [orders.md](orders.md) |
| Избранное (бета) | `/wishlist` | [wishlist.md](wishlist.md) |
| REST API | `/api/*` | [api.md](api.md) |

## Чего в продукте нет

Регистрации, восстановления пароля, онлайн-оплаты, отмены заказа и отслеживания доставки. Запросы на эти функции — пожелания, а не ошибки. Список запланированного — в [roadmap.md](roadmap.md).

## Деньги

Цены в каталоге — целые рубли. Суммы в корзине и заказе считаются в копейках и показываются в рублях без копеек, с пробелом между разрядами: `2 540 ₽`.
