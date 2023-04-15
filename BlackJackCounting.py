import sys
from random import shuffle

import numpy as np
import scipy.stats as stats
import pylab as pl
import matplotlib.pyplot as plt
import copy
import time
import sqlite3
from sqlite3 import Error

from importer.StrategyImporter import StrategyImporter

SHOE_SIZE = 8
SHOE_PENETRATION = 0.5
BET_SPREAD = 20.0
BET_SPREAD_6 = 10.0
BET_SPREAD_5 = 5.0
BET_SPREAD_4 = 3.0
BET_SPREAD_3 = 2.0

DECK_SIZE = 52.0
CARDS = {"Ace": 11, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10, "Jack": 10, "Queen": 10, "King": 10}
BASIC_OMEGA_II = {"Ace": 0, "Two": 1, "Three": 1, "Four": 2, "Five": 2, "Six": 2, "Seven": 1, "Eight": 0, "Nine": -1, "Ten": -2, "Jack": -2, "Queen": -2, "King": -2}

BLACKJACK_RULES = {
    'triple7': False,  # Count 3x7 as a blackjack
}

STRATEGY = ""
HARD_STRATEGY = {}
SOFT_STRATEGY = {}
PAIR_STRATEGY = {}

class Card(object):
    """
    Represents a playing card with name and value.
    """
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __str__(self):
        return "%s" % self.name


class Shoe(object):
    """
    Represents the shoe, which consists of a number of card decks.
    """
    reshuffle = False

    def __init__(self, decks):
        self.count = 0
        self.count_history = []
        self.ideal_count = {}
        self.decks = decks
        self.cards = self.init_cards()
        self.init_count()

    def __str__(self):
        s = ""
        for c in self.cards:
            s += "%s\n" % c
        return s

    def init_cards(self):
        """
        Initialize the shoe with shuffled playing cards and set count to zero.
        """
        self.count = 0
        self.count_history.append(self.count)

        cards = []
        for d in range(self.decks):
            for c in CARDS:
                for i in range(0, 4):
                    cards.append(Card(c, CARDS[c]))
        shuffle(cards)
        return cards

    def init_count(self):
        """
        Keep track of the number of occurrences for each card in the shoe in the course over the game. ideal_count
        is a dictionary containing (card name - number of occurrences in shoe) pairs
        """
        for card in CARDS:
            self.ideal_count[card] = 4 * SHOE_SIZE

    def deal(self):
        """
        Returns:    The next card off the shoe. If the shoe penetration is reached,
                    the shoe gets reshuffled.
        """
        if self.shoe_penetration() < SHOE_PENETRATION:
            self.reshuffle = True
        card = self.cards.pop()

        assert self.ideal_count[card.name] > 0, "Either a cheater or a bug!"
        self.ideal_count[card.name] -= 1

        self.do_count(card)
        return card

    def deal_card(self, card):
        """
        Returns:    The next card off the shoe. If the shoe penetration is reached,
                    the shoe gets reshuffled.
        """
        if self.shoe_penetration() < SHOE_PENETRATION:
            self.reshuffle = True
        card1 = self.cards.pop()

        assert self.ideal_count[card.name] > 0, "Either a cheater or a bug!"
        self.ideal_count[card.name] -= 1

        self.do_count(card)
        return card

    def total_card(self):
        total_cards = 0
        for card in CARDS:
            total_cards += self.ideal_count[card]
        return total_cards

    def do_count(self, card):
        """
        Add the dealt card to current count.
        """
        self.count += BASIC_OMEGA_II[card.name]
        self.count_history.append(self.truecount())

    def truecount(self):
        """
        Returns: The current true count.
        """
        truecounter=self.count / (self.decks * self.shoe_penetration())
        #print(truecounter)
        return truecounter

    def shoe_penetration(self):
        """
        Returns: Ratio of cards that are still in the shoe to all initial cards.
        """
        return len(self.cards) / (DECK_SIZE * self.decks)


class Hand(object):
    """
    Represents a hand, either from the dealer or from the player
    """
    _value = 0
    _aces = []
    _aces_soft = 0
    splithand = False
    surrender = False
    doubled = False

    def __init__(self, cards):
        self.cards = cards

    def __str__(self):
        h = ""
        for c in self.cards:
            h += "%s " % c
        return h

    @property
    def value(self):
        """
        Returns: The current value of the hand (aces are either counted as 1 or 11).
        """
        self._value = 0
        for c in self.cards:
            self._value += c.value

        if self._value > 21 and self.aces_soft > 0:
            for ace in self.aces:
                if ace.value == 11:
                    self._value -= 10
                    ace.value = 1
                    if self._value <= 21:
                        break

        return self._value

    @property
    def aces(self):
        """
        Returns: The all aces in the current hand.
        """
        self._aces = []
        for c in self.cards:
            if c.name == "Ace":
                self._aces.append(c)
        return self._aces

    @property
    def aces_soft(self):
        """
        Returns: The number of aces valued as 11
        """
        self._aces_soft = 0
        for ace in self.aces:
            if ace.value == 11:
                self._aces_soft += 1
        return self._aces_soft

    def soft(self):
        """
        Determines whether the current hand is soft (soft means that it consists of aces valued at 11).
        """
        if self.aces_soft > 0:
            return True
        else:
            return False

    def splitable(self):
        """
        Determines if the current hand can be splitted.
        """
        if self.length() == 2 and self.cards[0].name == self.cards[1].name:
            return True
        else:
            return False

    def blackjack(self):
        """
        Check a hand for a blackjack, taking the defined BLACKJACK_RULES into account.
        """
        if not self.splithand and self.value == 21:
            if all(c.value == 7 for c in self.cards) and BLACKJACK_RULES['triple7']:
                return True
            elif self.length() == 2:
                return True
            else:
                return False
        else:
            return False

    def busted(self):
        """
        Checks if the hand is busted.
        """
        if self.value > 21:
            return True
        else:
            return False

    def add_card(self, card):
        """
        Add a card to the current hand.
        """
        self.cards.append(card)

    def split(self):
        """
        Split the current hand.
        Returns: The new hand created from the split.
        """
        self.splithand = True
        c = self.cards.pop()
        new_hand = Hand([c])
        new_hand.splithand = True
        return new_hand

    def length(self):
        """
        Returns: The number of cards in the current hand.
        """
        return len(self.cards)


class Player(object):
    """
    Represent a player
    """
    def __init__(self, hand=None, dealer_hand=None):
        self.hands = [hand]
        self.dealer_hand = dealer_hand

    def set_hands(self, new_hand, new_dealer_hand):
        self.hands = [new_hand]
        self.dealer_hand = new_dealer_hand

    def translate_card(self, card):
        if card == "1":
            card = "Ace"
        elif card == "2":
            card = "Two"
        elif card == "3":
            card = "Three"
        elif card == "4":
            card = "Four"
        elif card == "5":
            card = "Five"
        elif card == "6":
            card = "Six"
        elif card == "7":
            card = "Seven"
        elif card == "8":
            card = "Eight"
        elif card == "9":
            card = "Nine"
        elif card == "10":
            card = "Ten"
        elif card == "j":
            card = "Jack"
        elif card == "q":
            card = "Queen"
        elif card == "k":
            card = "King"
        return card

    def play_hand(self, hand, shoe):
        if hand.length() < 2:
            if hand.cards[0].name == "Ace":
                hand.cards[0].value = 11
            self.hit(hand, shoe)

        while not hand.busted() and not hand.blackjack():
            if hand.soft():
                flag = SOFT_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            elif hand.splitable():
                flag = PAIR_STRATEGY[hand.value][self.dealer_hand.cards[0].name]
            else:
                flag = HARD_STRATEGY[hand.value][self.dealer_hand.cards[0].name]

            if flag == 'D':
                if hand.length() == 2:
                    # print "Double Down"
                    hand.doubled = True
                    self.hit(hand, shoe)
                    break
                else:
                    flag = 'H'

            if flag == 'Sr':
                if hand.length() == 2:
                    # print "Surrender"
                    hand.surrender = True
                    break
                else:
                    flag = 'H'

            if flag == 'H':
                self.hit(hand, shoe)

            if flag == 'P':
                self.split(hand, shoe)

            if flag == 'S':
                break

    def hit_card(self, hand, shoe, card):
        c = shoe.deal_card(card)
        hand.add_card(c)
        # print "Hitted: %s" % c

    def hit(self, hand, shoe):
        c = shoe.deal()
        hand.add_card(c)
        # print "Hitted: %s" % c

    def split(self, hand, shoe):
        self.hands.append(hand.split())
        # print "Splitted %s" % hand
        self.play_hand(hand, shoe)


class Dealer(object):
    """
    Represent the dealer
    """
    def __init__(self, hand=None):
        self.hand = hand

    def set_hand(self, new_hand):
        self.hand = new_hand

    def play(self, shoe):
        while self.hand.value < 17:
            self.hit(shoe)

    def hit(self, shoe):
        c = shoe.deal()
        self.hand.add_card(c)
        # print "Dealer hitted: %s" %c

    # Returns an array of 6 numbers representing the probability that the final score of the dealer is
    # [17, 18, 19, 20, 21, Busted] '''
    # TODO Differentiate 21 and BJ
    # TODO make an actual tree, this is false AF
    def get_probabilities(self) :
        start_value = self.hand.value
        # We'll draw 5 cards no matter what an count how often we got 17, 18, 19, 20, 21, Busted

class Game(object):
    """
    A sequence of Blackjack Rounds that keeps track of total money won or lost
    """
    def __init__(self):
        self.shoe = Shoe(SHOE_SIZE)
        self.money = 0.0
        self.bet = 0.0
        self.stake = 1.0
        self.player = Player()
        self.dealer = Dealer()
        self.count_higher_bet = 0

    def get_hand_winnings(self, hand):
        win = 0.0
        bet = self.stake
        if hand.busted():
            status = "LOST"
        else:
            if hand.blackjack():
                if self.dealer.hand.blackjack():
                    status = "PUSH"
                else:
                    status = "WON 3:2"
            elif self.dealer.hand.busted():
                status = "WON"
            elif self.dealer.hand.value < hand.value:
                status = "WON"
            elif self.dealer.hand.value > hand.value:
                status = "LOST"
            elif self.dealer.hand.value == hand.value:
                if self.dealer.hand.blackjack():
                    status = "LOST"  # player's 21 vs dealers blackjack
                else:
                    status = "PUSH"

        if status == "LOST":
            win += -1
        elif status == "WON":
            win += 1
        elif status == "WON 3:2":
            win += 1.5
        elif status == "SURRENDER":
            win += -0.5
        if hand.doubled:
            win *= 2
            bet *= 2

        win *= self.stake

        return win, bet

    def translate_card(self, card):
        if card == "1":
            card = "Ace"
        elif card == "2":
            card = "Two"
        elif card == "3":
            card = "Three"
        elif card == "4":
            card = "Four"
        elif card == "5":
            card = "Five"
        elif card == "6":
            card = "Six"
        elif card == "7":
            card = "Seven"
        elif card == "8":
            card = "Eight"
        elif card == "9":
            card = "Nine"
        elif card == "10":
            card = "Ten"
        elif card == "j":
            card = "Jack"
        elif card == "q":
            card = "Queen"
        elif card == "k":
            card = "King"
        return card


    def play_round_simulation(self):
        while True:
            print("TRUECOUNT")
            #print(self.shoe.count_history)
            print(self.shoe.truecount())
            if self.shoe.truecount() <= 3 and self.shoe.truecount() > 2.5:
                self.stake = BET_SPREAD_3
                self.count_higher_bet+=1
            elif self.shoe.truecount() <= 4 and self.shoe.truecount() > 3:
                self.stake = BET_SPREAD_4
                self.count_higher_bet+=1
            elif self.shoe.truecount() <= 5 and self.shoe.truecount() > 4:
                self.stake = BET_SPREAD_5
                self.count_higher_bet+=1
            elif self.shoe.truecount() <= 6 and self.shoe.truecount() > 5 :
                self.stake = BET_SPREAD_6
                self.count_higher_bet+=1
            elif self.shoe.truecount() > 6:
                self.stake = BET_SPREAD
                self.count_higher_bet+=1
            else:
                self.stake = 1.0

            print("------ Bet:" + str(self.stake) + "------")

            print("Dealer round = d | Ace = 1 | Jack = j | Queen = q | King = k | 2, 3, 4, 5, 6, 7, 8, 9")
            dealer_card = input("Input Dealer's card: ")
            dealer_card = self.translate_card(dealer_card)
            dealer_hand = Hand([self.shoe.deal_card(Card(dealer_card, CARDS[dealer_card]))])
            self.dealer.set_hand(dealer_hand)

            self.blackjackSecurity = False
            if self.dealer.hand.cards[0].name == "Ace":
                #print("----------------------")
                #print("Dealer hand:")
                #print(dealer_hand.__str__())
                winning_chances = self.check_insurance()
                print("Insurance winning chances: ")
                print(winning_chances)
                if winning_chances >= 0.5:
                    self.blackjackSecurity = True
                    print("---------------")
                    print("CALL INSURANCE")
                    print("---------------")

            print("Input other's card")
            while True:
                other_card = input()
                #if other_card == "e":
                if other_card == "d":
                    print("Input Dealer's draw cards: ")
                    while self.dealer.hand.value < 17:
                        dealer_card = self.translate_card(input())
                        self.dealer.hand.add_card(self.shoe.deal_card(Card(dealer_card, CARDS[dealer_card])))
                    break
                    #print("Input all the other's card, then end round with 'e'")
                else:
                    other_card = self.translate_card(other_card)
                    self.shoe.deal_card(Card(other_card, CARDS[other_card]))
                    print(self.shoe.truecount())
                    

            check = input("Input 1 if shoe is shuffled")
            if check == '1':
                break
        

    def check_insurance(self):
        winnable = 0
        total = 0
        for card in CARDS:
            if card=="Ten" or card=="Jack" or card=="Queen" or card=="King":
                winnable += self.shoe.ideal_count[card]

            total += self.shoe.ideal_count[card]

        return winnable/total

    def get_money(self):
        return self.money

    def get_count_higher_bet(self):
        return self.count_higher_bet

    def get_bet(self):
        return self.bet

if __name__ == "__main__":
    importer = StrategyImporter(sys.argv[1])
    HARD_STRATEGY, SOFT_STRATEGY, PAIR_STRATEGY = importer.import_player_strategy()

    while True:
        print("--------------New game--------------")
        game = Game()
        game.play_round_simulation()