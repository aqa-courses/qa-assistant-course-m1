import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

export const USERS = {
  alice: { email: 'alice@example.com', password: 'password123' },
  restricted: { email: 'restricted@example.com', password: 'password123' },
  locked: { email: 'locked@example.com', password: 'password123' },
} as const;

export type UserName = keyof typeof USERS;

/** Thin client for Shoplite's REST API: test data goes through the API, checks through the UI. */
export class ShopApi {
  constructor(private readonly request: APIRequestContext, private token = '') {}

  private get headers(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  async reset(): Promise<void> {
    const r = await this.request.post('/__reset', { headers: chaosHeaders() });
    expect(r.ok(), `POST /__reset: ${r.status()}`).toBeTruthy();
  }

  async login(user: UserName): Promise<string> {
    const r = await this.request.post('/api/login', { data: USERS[user] });
    expect(r.ok(), `login as ${user}: ${r.status()}`).toBeTruthy();
    this.token = (await r.json()).token;
    return this.token;
  }

  async productId(name: string): Promise<number> {
    const r = await this.request.get('/api/products');
    expect(r.ok(), `GET /api/products: ${r.status()}`).toBeTruthy();
    const product = (await r.json()).find((p: { name: string }) => p.name === name);
    expect(product, `product "${name}" in the seed data`).toBeTruthy();
    return product.id;
  }

  async addToCart(name: string, qty = 1): Promise<void> {
    const r = await this.request.post('/api/cart/items', {
      headers: this.headers,
      data: { product_id: await this.productId(name), qty },
    });
    expect(r.ok(), `add "${name}" to cart: ${r.status()}`).toBeTruthy();
  }
}

function chaosHeaders(): Record<string, string> {
  const token = process.env.CHAOS_TOKEN;
  return token ? { 'X-Chaos-Token': token } : {};
}

type Fixtures = {
  api: ShopApi;
  /** Logs a user in through the API and puts the session cookie into the browser. */
  loginAs: (user: UserName) => Promise<ShopApi>;
};

export const test = base.extend<Fixtures>({
  api: async ({ request }, use) => {
    const api = new ShopApi(request);
    await api.reset();
    await use(api);
  },
  loginAs: async ({ api, request, page, baseURL }, use) => {
    await use(async (user) => {
      const userApi = new ShopApi(request);
      const token = await userApi.login(user);
      await page.context().addCookies([{ name: 'sid', value: token, url: baseURL! }]);
      return userApi;
    });
  },
});

/** Shoplite formats money as "2 540 ₽". */
export const rub = (amount: number) => `${amount.toLocaleString('en-US').replace(/,/g, ' ')} ₽`;

export async function openCart(page: Page) {
  await page.goto('/cart');
  await expect(page.getByRole('heading', { name: 'Корзина' })).toBeVisible();
}

export { expect };
