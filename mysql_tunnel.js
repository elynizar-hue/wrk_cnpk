const net = require('net');
const mysql = require('mysql2/promise');

const MYSQL_HOST = process.env.MYSQL_HOST || 'canpack-elynizar-dd70.h.aivencloud.com';
const MYSQL_PORT = parseInt(process.env.MYSQL_PORT || '10132', 10);
const MYSQL_USER = process.env.MYSQL_USER || 'avnadmin';
const MYSQL_PASSWORD = process.env.MYSQL_PASSWORD;
const MYSQL_DATABASE = process.env.MYSQL_DATABASE || 'defaultdb';
const LISTEN_PORT = parseInt(process.env.LISTEN_PORT || '3306', 10);

let connection;

async function connectMySQL() {
  try {
    connection = await mysql.createConnection({
      host: MYSQL_HOST,
      port: MYSQL_PORT,
      user: MYSQL_USER,
      password: MYSQL_PASSWORD,
      database: MYSQL_DATABASE,
      ssl: { rejectUnauthorized: false },
    });
    console.log(`[tunnel] Connected to MySQL ${MYSQL_HOST}:${MYSQL_PORT}`);
  } catch (err) {
    console.error('[tunnel] MySQL connection failed:', err.message);
    process.exit(1);
  }
}

const server = net.createServer((client) => {
  console.log('[tunnel] New local connection');
  const mysqlStream = connection.stream;

  client.on('error', (err) => {
    console.error('[tunnel] Local client error:', err.message);
  });

  mysqlStream.on('error', (err) => {
    console.error('[tunnel] MySQL stream error:', err.message);
    client.end();
  });

  client.pipe(mysqlStream).pipe(client);

  client.on('end', () => {
    console.log('[tunnel] Local connection closed');
  });
});

server.listen(LISTEN_PORT, '127.0.0.1', async () => {
  await connectMySQL();
  console.log(`[tunnel] Listening on 127.0.0.1:${LISTEN_PORT}`);
  console.log('[tunnel] Press Ctrl+C to stop');
});

process.on('SIGINT', async () => {
  console.log('\n[tunnel] Shutting down...');
  if (connection) await connection.end();
  server.close();
  process.exit(0);
});
