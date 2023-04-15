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
SHOE_PENETRATION = 0.25

DECK_SIZE = 52.0
CARDS = {"Ace": 11, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10}

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
                if c == "Ten":
                    for i in range(0, 16):
                        cards.append(Card(c, CARDS[c]))
                else:
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
            if card=="Ten":
                self.ideal_count[card] *= 4

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

        return card

    def deal_card(self, card):
        """
        Returns:    The next card off the shoe. If the shoe penetration is reached,
                    the shoe gets reshuffled.
        """
        if self.shoe_penetration() < SHOE_PENETRATION:
            self.reshuffle = True

        assert self.ideal_count[card.name] > 0, "Either a cheater or a bug!"
        self.ideal_count[card.name] -= 1

        return card

    def total_card(self):
        total_cards = 0
        for card in CARDS:
            total_cards += self.ideal_count[card]
        return total_cards

    def truecount(self):
        """
        Returns: The current true count.
        """
        return self.count / (self.decks * self.shoe_penetration())

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

    def calculate_percentage(self, hand, shoe, possibilities, possibility=1):
        #print("Possibilities")
        #print(possibilities)
        for card in CARDS:
            if shoe.ideal_count[card]>0:
                copy_shoe = copy.deepcopy(shoe)
                copy_hand = copy.deepcopy(hand)
                new_possibility = possibility * copy_shoe.ideal_count[card]/copy_shoe.total_card()
                self.hit_card(copy_hand, copy_shoe, Card(card, CARDS[card]))
                
                if copy_hand.value == 17:
                    possibilities["17"] += new_possibility
                elif copy_hand.value == 18:
                    possibilities["18"] += new_possibility
                elif copy_hand.value == 19:
                    possibilities["19"] += new_possibility
                elif copy_hand.value == 20:
                    possibilities["20"] += new_possibility
                elif copy_hand.value == 21:
                    possibilities["21"] += new_possibility
                elif copy_hand.value > 21:
                    possibilities["Busted"] += new_possibility
                    start = False
                    for y in CARDS:
                        if start:
                            others_possibility = possibility * copy_shoe.ideal_count[y]/copy_shoe.total_card()
                            possibilities["Busted"] += others_possibility
                        if y == card:
                            start = True
                    break
                else:
                    self.calculate_percentage(copy_hand, copy_shoe, possibilities, new_possibility)

    def hit_card(self, hand, shoe, card):
        c = shoe.deal_card(card)
        hand.add_card(c)
        # print "Hitted: %s" % c

class Database:
    def __init__(self, path):
        self.create_connection(path)
        self.create_tables()

    def create_connection(self, path):
        try:
            self.connection = sqlite3.connect(path)
            #print("Connection to SQLite DB successful")
        except Error as e:
            print(f"The error '{e}' occurred")

    def execute_query(self, query):
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            self.connection.commit()
            #print("Query executed successfully")
        except Error as e:
            print(f"The error '{e}' occurred")
        
    def select_table(self, query, arguments):
        cur = self.connection.cursor()
        #print("Select on table")
        cur.execute(query, arguments)
        self.connection.commit()
        return cur.fetchall()

    def create_tables(self):
        cur = self.connection.cursor()
        #print("Creating tables")

        cur.execute(
            """CREATE TABLE IF NOT EXISTS BLACKJACK_CHANCES(
                id integer PRIMARY KEY AUTOINCREMENT,
                dealer text NOT NULL,
                Ace integer NOT NULL,
                Two integer NOT NULL,
                Three integer NOT NULL,
                Four integer NOT NULL,
                Five integer NOT NULL,
                Six integer NOT NULL,
                Seven integer NOT NULL,
                Eight integer NOT NULL,
                Nine integer NOT NULL,
                Ten integer NOT NULL,
                Seventeen real NOT NULL,
                Eightteen real NOT NULL,
                Nineteen real NOT NULL,
                Twenty real NOT NULL,
                Twentyone real NOT NULL,
                Busted real NOT NULL
                );""")

        self.connection.commit()
        
    def insert_update_table(self, query, arguments):
        cur = self.connection.cursor()
        cur.execute(query, arguments)
        self.connection.commit()
        #self.logger.info("Insert/Update on table successfully")

if __name__ == "__main__":
    database = Database("./database/bj_database.sqlite")
    f = open("BlackjackFillDealerChances.log", "w")
    shoe = Shoe(SHOE_SIZE)

    for card_1 in CARDS:
        dealer = Dealer()
        copy_shoe_1 = copy.deepcopy(shoe)
        dealer_hand = Hand([copy_shoe_1.deal_card(Card(card_1, CARDS[card_1]))])
        dealer.set_hand(dealer_hand)
        for card_2 in CARDS:
            start = False
            copy_shoe_2 = copy.deepcopy(copy_shoe_1)
            copy_shoe_2.deal_card(Card(card_2, CARDS[card_2]))
            for card_3 in CARDS:
                if card_3 == card_2:
                    start = True
                if start:
                    copy_shoe_3 = copy.deepcopy(copy_shoe_2)
                    copy_shoe_3.deal_card(Card(card_3, CARDS[card_3]))
                    copy_shoe_4 = copy.deepcopy(copy_shoe_3)

                    while copy_shoe_4.ideal_count["Ten"]>=0:

                        if copy_shoe_4.ideal_count["Ace"] < 0:
                            copy_shoe_4.ideal_count["Ace"]=copy_shoe_3.ideal_count["Ace"]
                            copy_shoe_4.ideal_count["Two"]-=1
                        if copy_shoe_4.ideal_count["Two"] < 0:
                            copy_shoe_4.ideal_count["Two"]=copy_shoe_3.ideal_count["Two"]
                            copy_shoe_4.ideal_count["Three"]-=1
                        if copy_shoe_4.ideal_count["Three"] < 0:
                            copy_shoe_4.ideal_count["Three"]=copy_shoe_3.ideal_count["Three"]
                            copy_shoe_4.ideal_count["Four"]-=1
                        if copy_shoe_4.ideal_count["Four"] < 0:
                            copy_shoe_4.ideal_count["Four"]=copy_shoe_3.ideal_count["Four"]
                            copy_shoe_4.ideal_count["Five"]-=1
                        if copy_shoe_4.ideal_count["Five"] < 0:
                            copy_shoe_4.ideal_count["Five"]=copy_shoe_3.ideal_count["Five"]
                            copy_shoe_4.ideal_count["Six"]-=1
                        if copy_shoe_4.ideal_count["Six"] < 0:
                            copy_shoe_4.ideal_count["Six"]=copy_shoe_3.ideal_count["Six"]
                            copy_shoe_4.ideal_count["Seven"]-=1
                        if copy_shoe_4.ideal_count["Seven"] < 0:
                            copy_shoe_4.ideal_count["Seven"]=copy_shoe_3.ideal_count["Seven"]
                            copy_shoe_4.ideal_count["Eight"]-=1
                        if copy_shoe_4.ideal_count["Eight"] < 0:
                            copy_shoe_4.ideal_count["Eight"]=copy_shoe_3.ideal_count["Eight"]
                            copy_shoe_4.ideal_count["Nine"]-=1
                        if copy_shoe_4.ideal_count["Nine"] < 0:
                            copy_shoe_4.ideal_count["Nine"]=copy_shoe_3.ideal_count["Nine"]
                            copy_shoe_4.ideal_count["Ten"]-=1
                        if copy_shoe_4.ideal_count["Ten"]<0:
                            break
                        
                        if copy_shoe_4.shoe_penetration() > SHOE_PENETRATION:
                            dealer_possibilities = {"17": 0.0, "18": 0.0, "19": 0.0, "20": 0.0, "21": 0.0, "Busted": 0.0}
                            dealer.calculate_percentage(dealer.hand, copy_shoe_4, dealer_possibilities)
                            print("Counting cards")
                            print("Ace: " + str(copy_shoe_4.ideal_count["Ace"]) + " | " + "Two: " + str(copy_shoe_4.ideal_count["Two"]) + " | " + "Three: " + str(copy_shoe_4.ideal_count["Three"]) + " | " + 
                                "Four: " + str(copy_shoe_4.ideal_count["Four"]) + " | " + "Five: " + str(copy_shoe_4.ideal_count["Five"]) + " | " + "Six: " + str(copy_shoe_4.ideal_count["Six"]) + " | " + 
                                "Seven: " + str(copy_shoe_4.ideal_count["Seven"]) + " | " + "Eight: " + str(copy_shoe_4.ideal_count["Eight"]) + " | " + "Nine: " + str(copy_shoe_4.ideal_count["Nine"]) + " | " + 
                                "Ten: " + str(copy_shoe_4.ideal_count["Ten"]))
                            print(dealer_possibilities)
                            print(dealer_possibilities["17"] + dealer_possibilities["18"] + dealer_possibilities["19"] + dealer_possibilities["20"] + dealer_possibilities["21"] + dealer_possibilities["Busted"])

                            database.insert_update_table("""INSERT INTO BLACKJACK_CHANCES (
                                dealer, Ace, Two, Three, Four, Five, Six, Seven, Eight, Nine, Ten, Seventeen, Eightteen, Nineteen, Twenty, Twentyone, Busted) 
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                (dealer_hand.cards[0].name, copy_shoe_4.ideal_count["Ace"], copy_shoe_4.ideal_count["Two"], copy_shoe_4.ideal_count["Three"],
                                copy_shoe_4.ideal_count["Four"], copy_shoe_4.ideal_count["Five"], copy_shoe_4.ideal_count["Six"], copy_shoe_4.ideal_count["Seven"],
                                copy_shoe_4.ideal_count["Eight"], copy_shoe_4.ideal_count["Nine"], copy_shoe_4.ideal_count["Ten"], dealer_possibilities["17"],
                                dealer_possibilities["18"], dealer_possibilities["19"], dealer_possibilities["20"], dealer_possibilities["21"], dealer_possibilities["Busted"]))
                            
                            rows = database.select_table("""SELECT * FROM BLACKJACK_CHANCES WHERE dealer=? AND Ace=? AND Two=? AND Three=? AND Four=? AND Five=? AND Six=?
                                AND Seven=? AND Eight=? AND Nine=? AND Ten=? AND Seventeen=? AND Eightteen=? AND Nineteen=? AND Twenty=? AND Twentyone=? AND Busted=?""", 
                                (dealer_hand.cards[0].name, copy_shoe_4.ideal_count["Ace"], copy_shoe_4.ideal_count["Two"], copy_shoe_4.ideal_count["Three"],
                                copy_shoe_4.ideal_count["Four"], copy_shoe_4.ideal_count["Five"], copy_shoe_4.ideal_count["Six"], copy_shoe_4.ideal_count["Seven"],
                                copy_shoe_4.ideal_count["Eight"], copy_shoe_4.ideal_count["Nine"], copy_shoe_4.ideal_count["Ten"], dealer_possibilities["17"],
                                dealer_possibilities["18"], dealer_possibilities["19"], dealer_possibilities["20"], dealer_possibilities["21"], dealer_possibilities["Busted"]))

                            f.write("Dealer card: " + str(rows[0][1]) + "\n")
                            f.write("Ace: " + str(rows[0][2]) + " | " + "Two: " + str(rows[0][3]) + " | " + "Three: " + str(rows[0][4]) + " | " + 
                                "Four: " + str(rows[0][5]) + " | " + "Five: " + str(rows[0][6]) + " | " + "Six: " + str(rows[0][7]) + " | " + 
                                "Seven: " + str(rows[0][8]) + " | " + "Eight: " + str(rows[0][9]) + " | " + "Nine: " + str(rows[0][10]) + " | " + 
                                "Ten: " + str(rows[0][11]) + "\n")
                            f.write("17: " + str(rows[0][12]) + " | " + "18: " + str(rows[0][13]) + " | " + "19: " + str(rows[0][14]) + " | " + 
                                "20: " + str(rows[0][15]) + " | " + "21: " + str(rows[0][16]) + " | " + "Busted: " + str(rows[0][17]) + "\n")

                        #Retira uma carta
                        copy_shoe_4.ideal_count["Ace"] -= 1
    
    f.close()