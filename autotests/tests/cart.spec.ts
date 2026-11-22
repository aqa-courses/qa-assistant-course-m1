import { test, expect, openCart, rub } from './fixtures';

test.describe('Корзина', () => {
  test('товар из каталога попадает в корзину', { tag: ['@id:8', '@smoke'] }, async ({ loginAs, page }) => {
    await loginAs('alice');
    await page.goto('/catalog');
    const card = page.getByTestId('product-card').filter({ hasText: 'USB-C хаб' });
    await card.getByTestId('add-to-cart').click();

    await expect(page.getByTestId('cart-count')).toHaveText('1');
    await openCart(page);
    await expect(page.getByTestId('cart-item')).toHaveCount(1);
    await expect(page.getByTestId('cart-item')).toContainText('USB-C хаб');
  });

  test('не больше 5 штук одного товара', { tag: '@id:9' }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('USB-C хаб', 5);
    await page.goto('/catalog');
    const card = page.getByTestId('product-card').filter({ hasText: 'USB-C хаб' });
    await card.getByTestId('add-to-cart').click();

    await expect(page.getByTestId('note')).toContainText('не больше 5');
    await openCart(page);
    await expect(page.getByTestId('cart-item-qty')).toHaveValue('5');
  });

  test('SAVE10 уменьшает итог на 10%', { tag: ['@id:10', '@smoke'] }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('USB-C хаб'); // 2 490 ₽, not on sale
    await openCart(page);
    await page.getByTestId('promo-input').fill('SAVE10');
    await page.getByTestId('promo-apply').click();

    await expect(page.getByTestId('promo-active')).toHaveText('Действует: SAVE10');
    await expect(page.getByTestId('cart-subtotal')).toHaveText(rub(2490));
    await expect(page.getByTestId('cart-discount')).toHaveText(`−${rub(249)}`);
    await expect(page.getByTestId('cart-shipping')).toHaveText(rub(299));
    await expect(page.getByTestId('cart-total')).toHaveText(rub(2490 - 249 + 299));
  });

  test('SAVE10 не действует на товары со скидкой', { tag: '@id:11' }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('Беспроводная мышь'); // on sale
    await openCart(page);
    await page.getByTestId('promo-input').fill('SAVE10');
    await page.getByTestId('promo-apply').click();

    await expect(page.getByTestId('promo-note')).toContainText('не действует на товары со скидкой');
    await expect(page.getByTestId('cart-discount')).toHaveText('0 ₽');
  });

  test('доставка бесплатная от 5 000 ₽', { tag: '@id:12' }, async ({ loginAs, page }) => {
    const alice = await loginAs('alice');
    await alice.addToCart('Механическая клавиатура'); // 6 990 ₽
    await openCart(page);

    await expect(page.getByTestId('cart-shipping')).toHaveText('бесплатно');
    await expect(page.getByTestId('cart-total')).toHaveText(rub(6990));
    await expect(page.getByTestId('free-shipping-hint')).toHaveCount(0);
  });
});
