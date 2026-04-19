Feature: Notification Bell
  As an authenticated user
  I want to see notifications via the bell icon
  So that I stay informed about task updates

  Background:
    Given I am logged in as "test@example.com"

  Scenario: Notification badge shows unread count
    Given I have 3 unread notifications
    Then the notification bell should show badge "3"

  Scenario: Opening notification panel
    When I click the notification bell
    Then the notification panel should open
    And I should see my notifications listed

  Scenario: Marking notification as read
    Given the notification panel is open
    When I click on a notification
    Then the notification should be marked as read
    And the unread count should decrease by 1
