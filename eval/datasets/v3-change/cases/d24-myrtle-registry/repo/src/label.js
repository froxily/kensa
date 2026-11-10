const kleur = require('kleur');

exports.label = function label(text) {
  return kleur.cyan(text.trim());
};
