import random
import sys

def play_monty():
    print("Welcome to Three-Card Monte!")
    print("Find the Queen to win.")

    cards = ['Joker', 'Joker', 'Queen']

    while True:
        random.shuffle(cards)

        print("\nCards are shuffled: [1] [2] [3]")
        print("Which card is the Queen? (Enter 1, 2, or 3. 'q' to quit)")

        try:
            choice = input("> ")
        except EOFError:
            break

        if choice.lower() == 'q':
            print("Thanks for playing!")
            break

        if choice not in ['1', '2', '3']:
            print("Invalid choice. Please enter 1, 2, or 3.")
            continue

        choice_idx = int(choice) - 1

        print(f"You chose card {choice}. It is... {cards[choice_idx]}!")
        if cards[choice_idx] == 'Queen':
            print("You win!")
        else:
            print("You lose!")
            queen_idx = cards.index('Queen') + 1
            print(f"The Queen was card {queen_idx}.")

if __name__ == "__main__":
    try:
        play_monty()
    except KeyboardInterrupt:
        print("\nThanks for playing!")
