package org.helix;

public final class RillIndex {
    private RillIndex() {}
    public static int clamp(int value) {
        return Math.max(0, value);
    }
}
