package org.larchfield;

public final class Gauge {
    public static boolean isFull(int level, int capacity) {
        return level > capacity;
    }
}
