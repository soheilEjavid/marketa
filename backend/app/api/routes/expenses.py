from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import DatabaseSession
from app.models.entities import User as UserModel
from app.schemas.expense import (
    ExpenseCreate,
    ExpenseRead,
    ExpenseUpdate,
    SalaryAdvanceCreate,
    SalaryAdvanceRead,
    SalaryPaymentCreate,
    SalaryPaymentRead,
    SalaryPaymentUpdate,
)
from app.services import expenses as expense_service
from app.services.audit import record_audit
from app.services.auth import require_role

router = APIRouter(tags=["expenses"])

# General expenses: admin+manager, per docs/expense-management.md's explicit
# API spec (not extended to accountant — see Step 1 investigation notes).
EXPENSE_ROLES = ("admin", "manager")
# Salary/payroll: admin ONLY — the one place in this app where even
# *viewing* (not just editing) must be restricted, per the doc's explicit
# "حساسیت دسترسی" section. Applied to every route below, GET included.
SALARY_ROLES = ("admin",)


@router.get("/expenses", response_model=list[ExpenseRead])
async def list_expenses(
    database: DatabaseSession,
    from_date: date | None = None,
    to_date: date | None = None,
    _: UserModel = Depends(require_role(*EXPENSE_ROLES)),
):
    return expense_service.list_expenses(database, from_date=from_date, to_date=to_date)


@router.get("/expenses/categories", response_model=list[str])
async def list_expense_categories(
    database: DatabaseSession,
    _: UserModel = Depends(require_role(*EXPENSE_ROLES)),
):
    return expense_service.distinct_expense_categories(database)


@router.post("/expenses", response_model=ExpenseRead)
async def create_expense(
    data: ExpenseCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*EXPENSE_ROLES)),
):
    expense = expense_service.create_expense(database, data, created_by_user_id=current_user.id)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        entity_type="expense",
        entity_id=expense.id,
        details=f"{expense.category}, amount={expense.amount}",
    )
    return expense


@router.patch("/expenses/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: int,
    data: ExpenseUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*EXPENSE_ROLES)),
):
    expense = expense_service.get_expense(database, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    updated = expense_service.update_expense(database, expense, data)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        entity_type="expense",
        entity_id=updated.id,
        details=f"{updated.category}, amount={updated.amount}",
    )
    return updated


@router.get("/salary-advances", response_model=list[SalaryAdvanceRead])
async def list_salary_advances(
    database: DatabaseSession,
    employee_id: int | None = None,
    _: UserModel = Depends(require_role(*SALARY_ROLES)),
):
    advances = expense_service.list_salary_advances(database, employee_id=employee_id)
    return [expense_service.to_salary_advance_read(advance) for advance in advances]


@router.post("/salary-advances", response_model=SalaryAdvanceRead)
async def create_salary_advance(
    data: SalaryAdvanceCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*SALARY_ROLES)),
):
    try:
        advance = expense_service.create_salary_advance(database, data)
    except expense_service.EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        entity_type="salary_advance",
        entity_id=advance.id,
        details=f"employee={advance.employee_id}, amount={advance.amount}",
    )
    return expense_service.to_salary_advance_read(advance)


@router.get("/salary-payments", response_model=list[SalaryPaymentRead])
async def list_salary_payments(
    database: DatabaseSession,
    employee_id: int | None = None,
    _: UserModel = Depends(require_role(*SALARY_ROLES)),
):
    payments = expense_service.list_salary_payments(database, employee_id=employee_id)
    return [expense_service.to_salary_payment_read(payment) for payment in payments]


@router.post("/salary-payments", response_model=SalaryPaymentRead)
async def create_salary_payment(
    data: SalaryPaymentCreate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*SALARY_ROLES)),
):
    try:
        payment = expense_service.create_salary_payment(database, data, created_by_user_id=current_user.id)
    except expense_service.EmployeeNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except expense_service.DuplicateSalaryPaymentError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="create",
        entity_type="salary_payment",
        entity_id=payment.id,
        details=f"employee={payment.employee_id}, period={payment.period_year}/{payment.period_month}, net={payment.net_amount}",
    )
    return expense_service.to_salary_payment_read(payment)


@router.patch("/salary-payments/{payment_id}", response_model=SalaryPaymentRead)
async def update_salary_payment(
    payment_id: int,
    data: SalaryPaymentUpdate,
    database: DatabaseSession,
    current_user: UserModel = Depends(require_role(*SALARY_ROLES)),
):
    payment = expense_service.get_salary_payment(database, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Salary payment not found")
    updated = expense_service.update_salary_payment(database, payment, data)
    record_audit(
        database,
        user_id=current_user.id,
        username=current_user.username,
        action="update",
        entity_type="salary_payment",
        entity_id=updated.id,
        details=f"employee={updated.employee_id}, period={updated.period_year}/{updated.period_month}, net={updated.net_amount}",
    )
    return expense_service.to_salary_payment_read(updated)
