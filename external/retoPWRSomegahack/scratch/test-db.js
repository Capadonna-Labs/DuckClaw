import { query, ensureSchema } from './src/lib/motherduck.js';

async function testConnection() {
  console.log('--- TESTING MOTHERDUCK CONNECTION ---');
  try {
    await ensureSchema();
    const result = await query('SELECT 1 as connected');
    console.log('Connection successful:', result);
    
    const tables = await query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'");
    console.log('Available tables:', tables);
  } catch (err) {
    console.error('Connection failed:', err);
  }
}

testConnection();
