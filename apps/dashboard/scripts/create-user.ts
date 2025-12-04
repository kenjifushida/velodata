/**
 * User Creation Script
 *
 * Utility script to create admin users in the database.
 * Run with: npx tsx scripts/create-user.ts <username> <password>
 */
import { MongoClient } from 'mongodb';
import bcrypt from 'bcryptjs';
import { config } from 'dotenv';

// Load environment variables from .env.local
config({ path: '.env.local' });

async function createUser(username: string, password: string) {
  const uri = process.env.MONGODB_URI;

  if (!uri) {
    console.error('Error: MONGODB_URI not found in environment variables');
    console.error('Make sure .env.local exists and contains MONGODB_URI');
    process.exit(1);
  }

  console.log('Connecting to MongoDB...');
  const client = new MongoClient(uri);

  try {
    await client.connect();
    console.log('Connected to MongoDB');

    const db = client.db('velodata');
    const usersCollection = db.collection('users');

    // Check if user already exists
    const existingUser = await usersCollection.findOne({ username });
    if (existingUser) {
      console.error(`Error: User '${username}' already exists`);
      process.exit(1);
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Create user document
    const user = {
      username,
      password: hashedPassword,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    // Insert user
    await usersCollection.insertOne(user);

    console.log(`✓ User '${username}' created successfully`);
    console.log('\nYou can now login with:');
    console.log(`  Username: ${username}`);
    console.log(`  Password: ${password}`);
  } catch (error) {
    console.error('Error creating user:', error);
    process.exit(1);
  } finally {
    await client.close();
  }
}

// Parse command line arguments
const args = process.argv.slice(2);

if (args.length !== 2) {
  console.error('Usage: npx tsx scripts/create-user.ts <username> <password>');
  console.error('\nExample:');
  console.error('  npx tsx scripts/create-user.ts admin mypassword123');
  process.exit(1);
}

const [username, password] = args;

// Validate inputs
if (username.length < 3) {
  console.error('Error: Username must be at least 3 characters');
  process.exit(1);
}

if (password.length < 6) {
  console.error('Error: Password must be at least 6 characters');
  process.exit(1);
}

createUser(username, password);
