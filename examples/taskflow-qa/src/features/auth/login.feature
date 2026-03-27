Feature: User Login
  As a registered user
  I want to log in to TaskFlow
  So that I can manage my tasks

  Background:
    Given the TaskFlow application is running

  Scenario: Successful login with valid credentials
    Given I am on the login page
    When I enter email "test@example.com"
    And I enter password "Test1234!"
    And I click the login button
    Then I should be redirected to the task board
    And I should see my username in the header

  Scenario: Failed login with invalid password
    Given I am on the login page
    When I enter email "test@example.com"
    And I enter password "wrong-password"
    And I click the login button
    Then I should see an error message "Invalid credentials"
    And I should remain on the login page

  Scenario: Failed login with empty fields
    Given I am on the login page
    When I click the login button
    Then I should see validation errors
