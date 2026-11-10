<?php
$region = getenv('HEATHER_REGION');
if ($region === false || $region === '') {
    fwrite(STDERR, "HEATHER_REGION is required\n");
    exit(1);
}
echo "Region: ", $region, PHP_EOL;
