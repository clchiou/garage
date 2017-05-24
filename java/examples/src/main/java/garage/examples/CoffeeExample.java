package garage.examples;

import dagger.Component;
import dagger.Module;
import dagger.Provides;

import javax.inject.Inject;
import javax.inject.Singleton;

public class CoffeeExample {

    public interface Heater {
        void heat();
    }

    public interface Pump {
        void pump();
    }

    public static class ElectricHeater implements Heater {

        public ElectricHeater() {
            System.out.println("New heater");
        }

        @Override
        public void heat() {
            System.out.println("Heat...");
        }
    }

    public static class Thermosiphon implements Pump {

        private final Heater heater;

        @Inject
        public Thermosiphon(Heater heater) {
            System.out.println("New thermosiphon");
            this.heater = heater;
        }

        @Override
        public void pump() {
            System.out.print("Pump: ");
            heater.heat();
            System.out.println("Pump...");
        }
    }

    public static class CoffeeMaker {
        private final Heater heater;
        private final Pump pump;

        @Inject
        public CoffeeMaker(Heater heater, Pump pump) {
            System.out.println("New coffee maker");
            this.heater = heater;
            this.pump = pump;
        }

        public void brew() {
            System.out.println("Brew coffee...");
            heater.heat();
            pump.pump();
        }
    }

    @Module
    public static class DripCoffeeModule {

        @Provides @Singleton public static Heater provideHeater() {
            return new ElectricHeater();
        }

        @Provides public static Pump providePump(Thermosiphon pump) {
            return pump;
        }

        @Provides public static CoffeeMaker provideCoffeeMaker(
                Heater heater, Pump pump) {
            return new CoffeeMaker(heater, pump);
        }
    }

    @Component(modules = DripCoffeeModule.class)
    @Singleton
    public interface CoffeeShop {
        CoffeeMaker maker();
    }

    public static void main(String[] args) {
        CoffeeShop coffeeShop = DaggerCoffeeExample_CoffeeShop.create();
        coffeeShop.maker().brew();
    }
}
