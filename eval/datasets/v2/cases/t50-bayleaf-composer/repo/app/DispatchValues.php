<?php declare(strict_types=1);
namespace Bayleaf;

final class DispatchValues {
    public function batchLimit(string $value): int { return $value; }
    public function isReady(int $value): bool { return $value; }
    public function zoneName(int $value): string { return $value; }
    public function retryDelay(string $value): float { return $value; }
    public function attempts(bool $value): int { return $value; }
    public function deadline(): \DateTimeImmutable { return null; }
}
