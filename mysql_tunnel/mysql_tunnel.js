const net = require('net');
const tls = require('tls');
const dns = require('dns');
const { promisify } = require('util');

const resolve = promisify(dns.resolve);
const DEFAULT_HOST = 'canpack-elynizar-dd70.h.aivencloud.com';
const FALLBACK_IP = '206.189.12.172';
const MYSQL_PORT = parseInt(process.env.MYSQL_PORT || '10132', 10);
const LISTEN_PORT = parseInt(process.env.LISTEN_PORT || '3306', 10);

async function resolveHost() {
  try {
    const records = await resolve(DEFAULT_HOST, 'A');
    return records[0] || FALLBACK_IP;
  } catch (err) {
    console.warn(`[tunnel] DNS resolve failed for ${DEFAULT_HOST}, using fallback ${FALLBACK_IP}`);
    return FALLBACK_IP;
  }
}

async function startTunnel() {
  const host = await resolveHost();
  console.log(`[tunnel] Resolved ${DEFAULT_HOST} -> ${host}`);

  const server = net.createServer((client) => {
    console.log('[tunnel] New local connection');

    const mysqlSocket = tls.connect(
      {
        host: host,
        port: MYSQL_PORT,
        rejectUnauthorized: false,
      },
      () => {
        console.log(`[tunnel] TLS connected to ${host}:${MYSQL_PORT}`);
      }
    );

    mysqlSocket.on('error', (err) => {
      console.error('[tunnel] MySQL TLS error:', err.message);
      client.end();
    });

    client.on('error', (err) => {
      console.error('[tunnel] Local client error:', err.message);
      mysqlSocket.end();
    });

    client.pipe(mysqlSocket).pipe(client);

    client.on('end', () => {
      console.log('[tunnel] Local connection closed');
      mysqlSocket.end();
    });
  });

  server.listen(LISTEN_PORT, '127.0.0.1', () => {
    console.log(`[tunnel] Listening on 127.0.0.1:${LISTEN_PORT}`);
    console.log('[tunnel] Press Ctrl+C to stop');
  });

  return server;
}

startTunnel().catch((err) => {
  console.error('[tunnel] Failed to start:', err.message);
  process.exit(1);
});

process.on('SIGINT', () => {
  console.log('\n[tunnel] Shutting down...');
  process.exit(0);
});
