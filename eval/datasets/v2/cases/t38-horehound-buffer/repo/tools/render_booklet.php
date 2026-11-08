<?php
$sections = file('layout/booklet-sections.txt', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
foreach ($sections as $section) {
    echo "Preparing section: ", $section, PHP_EOL;
}
echo "Allocating page buffer", PHP_EOL;
$page = str_repeat('x', 48 * 1024 * 1024);
echo strlen($page), " bytes", PHP_EOL;
