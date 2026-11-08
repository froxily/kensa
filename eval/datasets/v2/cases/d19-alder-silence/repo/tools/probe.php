<?php
$target = getenv('ALDER_PROBE_URL');
if (!$target) {
    fwrite(STDERR, "probe URL is empty\n");
    exit(1);
}
$result = file_get_contents($target);
if ($result === false) {
    fwrite(STDERR, "probe request failed\n");
    exit(1);
}
echo "probe complete\n";
