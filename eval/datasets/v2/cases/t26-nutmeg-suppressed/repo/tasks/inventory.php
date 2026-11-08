<?php
$settings = parse_ini_file('settings/measurement-window.ini');
$values = json_decode(getenv('NUTMEG_MEASUREMENTS'), true);
if (!is_array($values) || count($values) === 0) { exit(1); }
foreach ($values as $value) {
    if (!is_numeric($value) || $value < $settings['minimum'] || $value > $settings['maximum']) { exit(1); }
}
echo count($values), " measurements\n";
