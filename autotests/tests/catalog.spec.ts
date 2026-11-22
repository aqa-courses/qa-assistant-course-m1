import { test, expect } from './fixtures';

test.describe('Каталог', () => {
  test.beforeEach(async ({ loginAs, page }) => {
    await loginAs('alice');
    await page.goto('/catalog');
  });

  test('поиск по названию не зависит от регистра', { tag: ['@id:4', '@smoke'] }, async ({ page }) => {
    await page.getByTestId('search-input').fill('МОНИТОР');
    await page.getByTestId('search-submit').click();

    await expect(page.getByTestId('product-title')).toHaveText(['Монитор 27"', 'Монитор 24"']);
    await expect(page.getByTestId('results-count')).toHaveText('Найдено товаров: 2');
  });

  test('поиск из одной буквы не фильтрует и подсказывает', { tag: '@id:5' }, async ({ page }) => {
    await page.getByTestId('search-input').fill('м');
    await page.getByTestId('search-submit').click();

    await expect(page.getByTestId('search-hint')).toBeVisible();
    await expect(page.getByTestId('product-card')).toHaveCount(12);
  });

  test('фильтр по категории и сортировка по цене', { tag: '@id:6' }, async ({ page }) => {
    await page.getByTestId('category-filter').selectOption('Мониторы');
    await page.getByTestId('sort').selectOption('price_asc');
    await page.getByTestId('search-submit').click();

    await expect(page.getByTestId('product-title')).toHaveText(['Монитор 24"', 'Монитор 27"']);
  });

  test('товар без остатка нельзя положить в корзину', { tag: '@id:7' }, async ({ page }) => {
    const card = page.getByTestId('product-card').filter({ hasText: 'Монитор 24"' });

    await expect(card.getByTestId('out-of-stock')).toBeDisabled();
    await expect(card.getByTestId('add-to-cart')).toHaveCount(0);
  });
});
