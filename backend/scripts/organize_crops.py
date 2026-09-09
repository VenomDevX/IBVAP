import os
import shutil

# Parent categories
CATEGORIES = {
    "People": ["Person"],
    "Vehicles": ["Car", "Bus", "Forklift", "Motorcycle", "Bicycle"],
    "Animals": ["Dog", "Cat", "Bird", "Horse", "Cow", "Sheep"],
    "Surveillance_Misc": ["License_Plate", "Night_Vision_Object"],
    "Military": [
        "Soldier",
        "Tank",
        "Generic_Jet",
        "Large_Military_Plane",
        "A10",
        "A400M",
        "AG600",
        "AH64",
        "AV8B",
        "An124",
        "An22",
        "An225",
        "An72",
        "B1",
        "B2",
        "B21",
        "B52",
        "Be200",
        "C130",
        "C17",
        "C2",
        "C390",
        "C5",
        "CH47",
        "CL415",
        "E2",
        "E7",
        "EF2000",
        "F117",
        "F14",
        "F15",
        "F16",
        "F18",
        "F22",
        "F35",
        "F4",
        "H6",
        "J10",
        "J20",
        "JAS39",
        "JF17",
        "JH7",
        "KC135",
        "KF21",
        "KJ600",
        "Ka27",
        "Ka52",
        "MQ9",
        "Mi24",
        "Mi28",
        "Mig29",
        "Mig31",
        "Mirage2000",
        "P3",
        "RQ4",
        "Rafale",
        "SR71",
        "Su24",
        "Su25",
        "Su34",
        "Su57",
        "TB001",
        "TB2",
        "Tornado",
        "Tu160",
        "Tu22M",
        "Tu95",
        "U2",
        "UH60",
        "US2",
        "V22",
        "Vulcan",
        "WZ7",
        "XB70",
        "Y20",
        "YF23",
        "Z19",
    ],
}


def organize_crops():
    base_dir = os.path.abspath(r"backend\data\cropped_classes")

    if not os.path.exists(base_dir):
        print(f"Error: {base_dir} does not exist.")
        return

    for parent_cat, sub_classes in CATEGORIES.items():
        parent_dir = os.path.join(base_dir, parent_cat)
        os.makedirs(parent_dir, exist_ok=True)

        for sub_class in sub_classes:
            sub_dir = os.path.join(base_dir, sub_class)

            # If the subclass folder exists at the root, move it into the parent folder
            if os.path.exists(sub_dir) and os.path.isdir(sub_dir):
                dest_dir = os.path.join(parent_dir, sub_class)
                print(f"Moving {sub_class} -> {parent_cat}/")
                shutil.move(sub_dir, dest_dir)

    print("\nSuccessfully organized all 91 classes into their Parent folders!")


if __name__ == "__main__":
    organize_crops()
