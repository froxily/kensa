<?php
$pageData = str_repeat('x', 256 * 1024);
for ($page = 1; $page <= 100; $page++) {
    $target = "/scratch/page-$page.bin";
    $file = fopen($target, 'wb');
    if ($file === false) exit(1);
    $written = fwrite($file, $pageData);
    fclose($file);
    if ($written !== strlen($pageData)) exit(1);
    echo "wrote scratch tile $page\n";
}
