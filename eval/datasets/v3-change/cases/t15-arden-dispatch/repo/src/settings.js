const region = process.env.ARDEN_DISPATCH_REGION;
if (!region) {
  throw new Error('ARDEN_DISPATCH_REGION is required');
}
module.exports = { region };
