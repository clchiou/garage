package g1.example.dagger;

public class AwesomeHeater implements Heater {
    private boolean heating = false;

    @Override
    public void on() {
        System.out.println("Heater on");
        heating = true;
    }

    @Override
    public void off() {
        System.out.println("Heater off");
        heating = false;
    }

    @Override
    public boolean isHot() {
        return heating;
    }
}
