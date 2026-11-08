package com.beech;
public class Summary {
    public static void main(String[] args) {
        Ledger ledger = new Ledger();
        int total = ledger.total();
        System.out.println(total);
    }
}
