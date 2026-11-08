<?php
$checks = [
    'trim spaces' => trim(' a ') === 'a',
    'lowercase' => strtolower('A') === 'a',
    'uppercase' => strtoupper('b') === 'B',
    'prefix' => str_starts_with('juniper', 'jun'),
    'suffix' => str_ends_with('juniper', 'per'),
    'length' => strlen('juniper') === 7,
    'separator' => implode('-', ['a', 'b']) === 'a-b',
    'split' => count(explode(',', 'a,b')) === 2,
    'replace' => str_replace('-', '_', 'a-b') === 'a_b',
    'empty' => trim(' ') === '',
];
echo "TAP version 13\n1..11\n";
$i = 0;
foreach ($checks as $label => $ok) {
    $i++;
    echo "# checking $label\n";
    echo ($ok ? 'ok ' : 'not ok ') . "$i - $label\n";
}
$settings = parse_ini_file(__DIR__ . '/../config/settings.ini');
echo "# checking configuration\n";
echo ($settings === false ? 'not ok ' : 'ok ') . "11 - configuration loads\n";
if ($settings === false || in_array(false, $checks, true)) exit(1);
