# VeloData Dashboard

High-frequency arbitrage platform dashboard for monitoring and filtering Japanese marketplace listings.

## Overview

This Next.js application provides a secure, authenticated dashboard for viewing and managing market listings scraped from Japanese marketplaces (Hard-Off, Mercari, Yahoo! Auctions).

## Features

- **JWT-based Authentication**: Secure login with httpOnly cookies and session management
- **Global State Management**: Zustand store for client-side authentication state
- **Server Components**: Direct MongoDB queries via Next.js Server Components for optimal performance
- **Advanced Filtering**: Filter by niche, source, price range, processing status
- **Full-text Search**: Search across titles and brands
- **Responsive Design**: Built with Tailwind CSS v4 and modern design patterns
- **Type Safety**: Full TypeScript implementation with Zod validation

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **Language**: TypeScript 5
- **Database**: MongoDB (direct connection via native driver)
- **Authentication**: JWT (jose library) + bcryptjs
- **State Management**: Zustand
- **Styling**: Tailwind CSS v4
- **Validation**: Zod

## Architecture

### Authentication Flow

1. User submits credentials via login form
2. Server action validates credentials and queries MongoDB users collection
3. JWT token created and stored in httpOnly cookie
4. Middleware validates token on protected routes
5. Zustand store syncs session state on client

### Data Flow

1. Dashboard page calls server actions to fetch market listings
2. Server actions query MongoDB with filters and pagination
3. Results rendered in Server Components for SEO and performance
4. Client components handle interactivity (filters, pagination)

### Security Features

- **httpOnly Cookies**: Prevents XSS attacks by making tokens inaccessible to JavaScript
- **CSRF Protection**: SameSite cookie attribute prevents cross-site request forgery
- **Password Hashing**: bcryptjs with salt rounds for secure password storage
- **JWT Expiration**: 7-day token expiration with automatic renewal
- **Middleware Protection**: All routes except login are protected by authentication middleware

## Getting Started

### Prerequisites

- Node.js 20+
- MongoDB running locally or remote connection
- Market listings already scraped (via Python scrapers)

### Installation

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
```bash
cp .env.example .env.local
```

Edit `.env.local`:
```env
MONGODB_URI=mongodb://localhost:27017/velodata
JWT_SECRET=your-secret-key-change-in-production
NODE_ENV=development
```

**Important**: Generate a secure JWT secret for production:
```bash
openssl rand -base64 32
```

3. Create your first admin user:
```bash
npx tsx scripts/create-user.ts admin yourpassword123
```

4. Start the development server:
```bash
npm run dev
```

5. Open [http://localhost:3000](http://localhost:3000)

The app will redirect to `/login` (unauthenticated) or `/dashboard` (authenticated).

## Project Structure

```
apps/dashboard/
├── app/
│   ├── actions/              # Server Actions
│   │   ├── auth.ts          # Login, logout, session management
│   │   └── market-listings.ts # Fetch, filter, search listings
│   ├── dashboard/           # Protected dashboard pages
│   │   ├── components/      # Dashboard UI components
│   │   │   ├── DashboardHeader.tsx
│   │   │   ├── StatsCards.tsx
│   │   │   ├── FilterPanel.tsx
│   │   │   ├── ListingsTable.tsx
│   │   │   └── Pagination.tsx
│   │   └── page.tsx
│   ├── login/               # Login page
│   │   └── page.tsx
│   ├── providers/           # Client-side providers
│   │   └── AuthProvider.tsx
│   ├── layout.tsx           # Root layout
│   └── page.tsx             # Home (redirects to dashboard)
├── lib/
│   ├── models/              # TypeScript types and schemas
│   │   ├── user.ts
│   │   └── market-listing.ts
│   ├── store/               # Zustand stores
│   │   └── auth-store.ts
│   ├── auth.ts              # JWT utilities
│   └── mongodb.ts           # MongoDB connection singleton
├── scripts/
│   └── create-user.ts       # User creation utility
├── middleware.ts            # Route protection middleware
└── .env.local               # Environment variables
```

## Usage

### Creating Users

```bash
# Create a new user
npx tsx scripts/create-user.ts <username> <password>

# Example
npx tsx scripts/create-user.ts admin mypassword123
```

### Login

1. Navigate to [http://localhost:3000/login](http://localhost:3000/login)
2. Enter username and password
3. Click "Sign In"

On successful login, you'll be redirected to the dashboard.

### Dashboard Features

#### Stats Overview
- Total listings count
- Processed vs. unprocessed listings
- Breakdown by niche (Pokemon Cards, Watches, Camera Gear)

#### Filtering
- **Niche**: Filter by product category
- **Source**: Filter by marketplace (Hard-Off, Mercari, Yahoo!)
- **Price Range**: Set min/max price in Japanese Yen
- **Status**: Show processed or unprocessed listings only
- **Search**: Full-text search on title and brand

#### Listings Table
- **Image**: Product thumbnail (if available)
- **Title**: Product name with brand
- **Niche**: Category badge
- **Source**: Marketplace name
- **Price**: JPY formatted price
- **Condition**: Color-coded condition rank (N, S, A, B, C, D, JUNK)
- **Status**: Processed/pending indicator
- **Actions**: Link to original listing

#### Pagination
- 20 items per page
- Page numbers with ellipsis for large datasets
- Previous/Next navigation

### Logout

Click the "Logout" button in the top-right corner of the dashboard header.

## API Reference

### Server Actions

#### `loginAction(formData)`
Authenticates user and creates session.

**Parameters:**
- `formData`: FormData containing `username` and `password`

**Returns:**
```typescript
{
  success: boolean;
  error?: string;
  user?: UserSession;
}
```

#### `logoutAction()`
Destroys session and redirects to login.

#### `getSessionAction()`
Retrieves current user session.

**Returns:** `UserSession | null`

#### `getMarketListings(filters)`
Fetches market listings with filters and pagination.

**Parameters:**
```typescript
{
  niche_type?: 'POKEMON_CARD' | 'WATCH' | 'CAMERA_GEAR';
  source_id?: 'HARDOFF' | 'MERCARI_JP' | 'YAHOO_AUCTIONS_JP';
  min_price?: number;
  max_price?: number;
  search?: string;
  is_processed?: boolean;
  page?: number;
  limit?: number;
}
```

**Returns:**
```typescript
{
  listings: MarketListing[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}
```

#### `getFilterOptions()`
Retrieves available filter options for dropdowns.

**Returns:**
```typescript
{
  nicheTypes: NicheType[];
  sources: SourceId[];
  priceRange: { min_price: number; max_price: number };
}
```

#### `getListingStats()`
Retrieves dashboard statistics.

**Returns:**
```typescript
{
  totalListings: number;
  processedListings: number;
  unprocessedListings: number;
  nicheBreakdown: Array<{ _id: string; count: number }>;
}
```

## MongoDB Collections

### `users`
Stores user credentials.

```typescript
{
  _id: ObjectId;
  username: string;
  password: string; // bcrypt hash
  createdAt: Date;
  updatedAt: Date;
}
```

### `market_listings`
Stores scraped marketplace listings (populated by Python scrapers).

```typescript
{
  _id: string;
  niche_type: 'POKEMON_CARD' | 'WATCH' | 'CAMERA_GEAR';
  source: {
    source_id: string;
    display_name: string;
    base_url: string;
  };
  title: string;
  price_jpy: number;
  url: string;
  image_url?: string;
  listed_at?: Date;
  created_at: Date;
  last_updated_at: Date;
  attributes: Record<string, any>;
  is_processed: boolean;
  matched_canonical_id?: string;
  potential_profit_usd?: number;
}
```

## Deployment

### Environment Variables

For production deployment, ensure:

1. **Generate secure JWT secret:**
```bash
openssl rand -base64 32
```

2. **Set production environment variables:**
```env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/velodata
JWT_SECRET=<generated-secret>
NODE_ENV=production
```

### Build

```bash
npm run build
```

### Start Production Server

```bash
npm start
```

### Vercel Deployment

1. Push to GitHub
2. Import project in Vercel
3. Set environment variables in Vercel dashboard
4. Deploy

## Development

### Run Development Server

```bash
npm run dev
```

### Type Checking

```bash
npx tsc --noEmit
```

### Linting

```bash
npm run lint
```

## Troubleshooting

### "Cannot connect to MongoDB"
- Ensure MongoDB is running locally or remote URI is correct
- Check `MONGODB_URI` in `.env.local`
- Verify network access if using MongoDB Atlas

### "Invalid username or password"
- Create user with `npx tsx scripts/create-user.ts`
- Verify credentials are correct
- Check users collection in MongoDB

### "Token verification failed"
- Clear browser cookies
- Check `JWT_SECRET` is set in `.env.local`
- Restart development server

### No listings showing
- Ensure Python scrapers have populated `market_listings` collection
- Run Hard-Off scraper: `python services/scrapers/hardoff_scraper.py --category watches --max-pages 1`
- Check MongoDB for documents: `db.market_listings.countDocuments()`

## Best Practices

### Security
- **Never commit `.env.local`** - Use `.env.example` template
- **Rotate JWT secrets** - Change periodically in production
- **Use HTTPS in production** - Required for secure cookies
- **Limit login attempts** - Consider adding rate limiting

### Performance
- **Server Components by default** - Only use `'use client'` when necessary
- **Optimize images** - Use Next.js Image component with proper sizing
- **Database indexes** - Ensure indexes on frequently queried fields:
  ```javascript
  db.market_listings.createIndex({ niche_type: 1 });
  db.market_listings.createIndex({ "source.source_id": 1 });
  db.market_listings.createIndex({ created_at: -1 });
  db.market_listings.createIndex({ price_jpy: 1 });
  ```

### Maintainability
- **Type everything** - Leverage TypeScript for safety
- **Server Actions for mutations** - Keep data fetching on server
- **Component composition** - Break down large components
- **Centralize validation** - Use Zod schemas consistently

## Future Enhancements

- [ ] Role-based access control (admin, viewer, analyst)
- [ ] Export listings to CSV/Excel
- [ ] Real-time updates with WebSockets
- [ ] Advanced analytics and charts
- [ ] Bulk operations (mark as processed, delete)
- [ ] Notification system for high-profit opportunities
- [ ] API keys for external integrations
- [ ] Audit logging for user actions

## License

Proprietary - VeloData Platform
