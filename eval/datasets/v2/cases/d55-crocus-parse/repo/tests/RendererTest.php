<?php
use PHPUnit\Framework\TestCase;

final class RendererTest extends TestCase {
    public function testTrim(): void { self::assertSame('a', trim(' a ')); }
    public function testUpper(): void { self::assertSame('A', strtoupper('a')); }
    public function testLower(): void { self::assertSame('a', strtolower('A')); }
    public function testPrefix(): void { self::assertTrue(str_starts_with('crocus', 'cro')); }
    public function testLength(): void { self::assertSame(6, strlen('crocus')); }
    public function testRendererSyntax(): void {
        $file = realpath(__DIR__ . '/../src/Renderer.php');
        exec(escapeshellarg(PHP_BINARY) . ' -l ' . escapeshellarg($file) . ' 2>&1', $output, $status);
        if ($status !== 0) fwrite(STDERR, implode("\n", $output) . "\n");
        self::assertSame(0, $status);
    }
}
