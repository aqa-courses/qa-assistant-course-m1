import { test, expect, openCart } from './fixtures';

const ADDRESS = 'Москва, ул. Тестовая, д. 1, кв. 2';

test.describe('Оформление заказа', () => {
  test('заказ оформляется и появляется в профиле', { tag: ['@id:13', '@smoke'] }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('Коврик для мыши XL');
    await openCart(page);
    await page.getByTestId('checkout-button').click();
    await page.getByTestId('checkout-address').fill(ADDRESS);
    await page.getByTestId('checkout-submit').click();

    await expect(page.getByTestId('order-confirmation')).toContainText('оформлен');
    await expect(page.getByTestId('order-address')).toHaveText(ADDRESS);
    const orderNumber = await page.getByTestId('order-number').innerText();

    await page.getByTestId('nav-profile').click();
    await expect(page.getByTestId('order-link')).toHaveText([orderNumber]);
    await expect(page.getByTestId('cart-count')).toHaveCount(0);
  });

  test('короткий адрес не принимается', { tag: '@id:14' }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('Коврик для мыши XL');
    await page.goto('/checkout');
    await page.getByTestId('checkout-address').fill('Москва');
    await page.getByTestId('checkout-submit').click();

    await expect(page.getByTestId('error')).toContainText('адрес');
    await expect(page.getByTestId('checkout-address')).toHaveValue('Москва');
  });

  test('ограниченная учётная запись не может оформить заказ', { tag: '@id:15' }, async ({ loginAs, page }) => {
    const restricted = await loginAs('restricted');
    await restricted.addToCart('Коврик для мыши XL');
    await page.goto('/checkout');
    await page.getByTestId('checkout-address').fill(ADDRESS);
    await page.getByTestId('checkout-submit').click();

    await expect(page.getByTestId('error')).toContainText('недоступно');
    await page.goto('/profile');
    await expect(page.getByTestId('no-orders')).toBeVisible();
  });
});
