namespace ParcelRates;

public static class RateTable
{
    public static decimal Cost(int grams) => grams * 0.02m;
    public static decimal Cost(int ounces) => ounces * 0.57m;
}
