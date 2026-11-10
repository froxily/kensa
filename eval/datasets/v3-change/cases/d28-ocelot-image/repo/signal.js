const port = Number(process.env.PORT || 3000);
require('node:http').createServer((req, res) => {
  res.end('signal ready\n');
}).listen(port);
