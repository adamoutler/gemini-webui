import time


def launch_rocket():
    print("🚀 Launching rocket to the moon...")
    for i in range(1, 4):
        print(f"Propulsion stage {i} engaged...")
        time.sleep(1)
    print("🌙 Arrived on the moon!")


def deliver_ice_cream():
    print("🍦 Delivering chocolate and vanilla ice cream to the lunar base...")
    time.sleep(2)
    print("✅ Ice cream successfully delivered! Enjoy!")


if __name__ == "__main__":
    launch_rocket()
    deliver_ice_cream()
