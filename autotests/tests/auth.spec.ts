import { test, expect, USERS } from './fixtures';

test.describe('Вход', () => {
  test.beforeEach(async ({ api, page }) => {
    await page.goto('/login');
  });

  test('покупатель входит и попадает в каталог', { tag: ['@id:1', '@smoke'] }, async ({ page }) => {
    await page.getByTestId('login-email').fill(USERS.alice.email);
    await page.getByTestId('login-password').fill(USERS.alice.password);
    await page.getByTestId('login-submit').click();

    await expect(page).toHaveURL(/\/catalog/);
    await expect(page.getByTestId('nav-profile')).toHaveText('Алиса');
  });

  test('неверный пароль: ошибка внутри формы', { tag: '@id:2' }, async ({ page }) => {
    await page.getByTestId('login-email').fill(USERS.alice.email);
    await page.getByTestId('login-password').fill('wrong-password');
    await page.getByTestId('login-submit').click();

    await expect(page.getByTestId('login-error')).toHaveText('Неверный email или пароль');
    await expect(page).toHaveURL(/\/login/);
  });

  test('заблокированный пользователь не может войти', { tag: '@id:3' }, async ({ page }) => {
    await page.getByTestId('login-email').fill(USERS.locked.email);
    await page.getByTestId('login-password').fill(USERS.locked.password);
    await page.getByTestId('login-submit').click();

    await expect(page.getByTestId('login-error')).toContainText('заблокирована');
  });
});
