            "target_name": step_target.name,
            "elapsed": 0.0,
            "duration": 3.2,
        })

        # If a house was just eliminated, dissolve its pact and purge all pending proposals to/from it
        if defender is not None and defender.is_eliminated():
            self.diplomacy.purge_eliminated(defender)

    def step_house_turn(self, house: House) -> None:
        """Execute the exact turn pipeline for a single AI house."""
        if house.is_eliminated() or self.winner is not None:
            return

        pending = house.get_pending_proposal()
        betray_target: House | None = None