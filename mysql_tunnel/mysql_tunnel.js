const net = require('net');
const tls = require('tls');

const MYSQL_HOST = process.env.MYSQL_HOST || 'canpack-elynizar-dd70.h.aivencloud.com';
const MYSQL_PORT = parseInt(process.env.MYSQL_PORT || '10132', 10);
const LISTEN_PORT = parseInt(process.env.LISTEN_PORT || '3306', 10);

const server = net.createServer((client) => {
  console.log('[tunnel] New local connection');

  const mysqlSocket = tls.connect(
    {
      host: MYSQL_HOST,
      port: MYSQL_PORT,
      rejectUnauthorized: false,
    },
    () => {
      console.log(`[tunnel] TLS connected to ${MYSQL_HOST}:${MYSQL_PORT}`);
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

process.on('SIGINT', () => {
  console.log('\n[tunnel] Shutting down...');
  server.close();
  process.exit(0);
});
