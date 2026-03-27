Feature: Task CRUD Operations
  As an authenticated user
  I want to create, read, update, and delete tasks
  So that I can manage my work

  Background:
    Given I am logged in as "test@example.com"
    And I am on the task board

  Scenario: Create a new task
    When I click "New Task"
    And I fill in the title "Write unit tests"
    And I fill in the description "Add tests for auth module"
    And I click "Create"
    Then I should see the task "Write unit tests" on the board
    And the task should have status "todo"

  Scenario: Update task status
    Given a task "Review PR" exists
    When I drag the task to the "in_progress" column
    Then the task "Review PR" should have status "in_progress"

  Scenario: Delete a task
    Given a task "Cleanup old branch" exists
    When I open the task detail
    And I click "Delete"
    And I confirm the deletion
    Then the task "Cleanup old branch" should not be visible on the board
