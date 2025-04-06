from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from typing import List
import auth
from models.employee import Employee
import logging
from models.interview import Interview
from models.company import Company
from models.users import User
from bson import ObjectId
import schemas

router = APIRouter()


@router.post("/signup", response_model=Employee)
async def signup(employee: schemas.Employee):
    existing_employee = await Employee.find_one(Employee.email == employee.email)
    if existing_employee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee with this email already exists",
        )

    existing_company = await Company.find_one(Company.name == employee.company_name)

    if not existing_company:
        company_doc = Company(
            name=employee.company_name,
            logo="",
            interview_settings={},
            employees=[],
        )
        await company_doc.insert()
        logging.info(f"Company {company_doc.name} created with ID: {company_doc.id}")
    else:
        company_doc = existing_company
        logging.info(f"Company {company_doc.name} already exists")

    hashed_password = auth.hash_password(employee.password)

    employee_data = Employee(
        email=employee.email,
        mobile_number=employee.mobile_number,
        password=hashed_password,
        name=employee.name,
        role_in_company=employee.role_in_company,
        company_name=company_doc.name,
    )
    await employee_data.insert()
    logging.info(f"Employee {employee_data.name} created with ID: {employee_data.id}")

    if company_doc.employees is None:
        company_doc.employees = []
    company_doc.employees.append(employee_data)
    await company_doc.save()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Employee created and linked to company successfully"},
    )


@router.post("/login")
async def login(employee: schemas.LoginEmployee):
    # Find the employee by email
    employee_found = await Employee.find_one(Employee.email == employee.email)

    if not employee_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    if not auth.verify_password(employee.password, employee_found.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
        )
    token = auth.create_access_token(data={"sub": employee.email})
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Login successful", "token": token},
    )


@router.get("/dashboard")
async def get_interviews(current_user: str = Depends(auth.get_current_user)):

    if current_user == "contact@prepsom.com":
        all_interviews = await Interview.find_all().to_list()
    else:
        employee = await Employee.find_one(Employee.email == current_user)
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        company = await Company.find_one(Company.name == employee.company_name)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
            )

        all_interviews = await Interview.find(
            Interview.company_id == company.id
        ).to_list()

    if not all_interviews:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No interviews found",
        )

    enhanced_interviews = []
    for interview in all_interviews:
        interview_dict = interview.model_dump()
        if "created_at" in interview_dict and interview_dict["created_at"]:
            interview_dict["created_at"] = interview_dict["created_at"].isoformat()
        interview_dict["id"] = str(interview.id)
        interview_dict["company_id"] = str(interview.company_id)
        interview_dict["user_id"] = str(interview.user_id)

        user = await interview.user_id.fetch()
        if user:
            # Add user information to the interview object
            interview_dict["user_name"] = user.name
            interview_dict["user_email"] = user.email
            interview_dict["user_mobile"] = user.mobile_number
            interview_dict["resume"] = user.resume_url()
        else:
            # If user not found, add empty values
            interview_dict["user_name"] = ""
            interview_dict["user_email"] = ""
            interview_dict["user_mobile"] = ""
            interview_dict["resume"] = ""

        # Select only specific fields
        filtered_interview_dict = {
            k: v
            for k, v in interview_dict.items()
            if k
            in [
                "id",
                "free_review",
                "user_id",
                "company_id",
                "created_at",
                "user_name",
                "user_email",
                "user_mobile",
                "resume",
                "user_data",
            ]
        }

        enhanced_interviews.append(filtered_interview_dict)

    return JSONResponse(status_code=status.HTTP_200_OK, content=enhanced_interviews)


@router.put("/company/{company_id}/employees")
async def add_employees_to_company(company_id: str, payload):

    try:
        company_obj_id = ObjectId(company_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid company_id")

    company_doc = await Company.get(company_obj_id)
    if not company_doc:
        raise HTTPException(status_code=404, detail="Company not found")

    new_employee_refs = []
    for emp_id in payload.employee_ids:
        try:
            emp_obj_id = ObjectId(emp_id)
        except:
            raise HTTPException(
                status_code=400, detail=f"Invalid employee_id: {emp_id}"
            )

        employee_doc = await Employee.get(emp_obj_id)
        if not employee_doc:
            raise HTTPException(status_code=404, detail=f"Employee {emp_id} not found")

        new_employee_refs.append(employee_doc)

    if company_doc.employees is None:
        company_doc.employees = []

    existing_ids = {emp.id for emp in company_doc.employees}
    for emp_doc in new_employee_refs:
        if emp_doc.id not in existing_ids:
            company_doc.employees.append(emp_doc)
            existing_ids.add(emp_doc.id)

    await company_doc.save()

    return {
        "message": "Employees added to company successfully",
    }
