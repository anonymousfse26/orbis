#include "llvm/IR/Module.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/Pass.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Support/Path.h"

#include <map>
#include <string>

using namespace llvm;

namespace {

struct VarTracerPass : public ModulePass {
    static char ID;
    VarTracerPass() : ModulePass(ID) {}

    std::map<const Value*, std::string> VarMap;

    static std::string getPathFromScope(const DIScope *Scope) {
        if (!Scope) return "<nofile>";
        const DIFile *File = Scope->getFile();
        if (!File) return "<nofile>";

        std::string Dir  = File->getDirectory().str();
        std::string Name = File->getFilename().str();

        if (sys::path::is_absolute(Name)) return Name;
        if (Dir.empty()) return Name;

        SmallString<256> P(Dir);
        sys::path::append(P, Name);
        return P.str().str();
    }

    static std::string getFileFromInst(const Instruction &I) {
        if (I.getDebugLoc()) {
            DebugLoc DL = I.getDebugLoc();           // DebugLoc
            if (auto *Loc = dyn_cast<DILocation>(DL.get())) { // MDNode* → DILocation*
                return getPathFromScope(Loc->getScope());
            }
        }
        return "<nofile>";
    }

    static std::string getFileFromFunction(const Function &F) {
        if (const DISubprogram *SP = F.getSubprogram()) {
            return getPathFromScope(SP);
        }
        return "<nofile>";
    }

    static Value* toI64(IRBuilder<> &B, Value *V, bool signExtend = true) {
        Type *T = V->getType();
        if (!T->isIntegerTy()) return V;
        unsigned BW = cast<IntegerType>(T)->getBitWidth();
        if (BW == 64) return V;
        if (BW < 64) return signExtend ? B.CreateSExt(V, B.getInt64Ty())
                                       : B.CreateZExt(V, B.getInt64Ty());
        return B.CreateTrunc(V, B.getInt64Ty());
    }

    void buildVarMap(Function &F) {
        for (BasicBlock &BB : F) {
            for (Instruction &I : BB) {
                if (auto *Dbg = dyn_cast<DbgDeclareInst>(&I)) {
                    if (DILocalVariable *Var = Dbg->getVariable()) {
                        if (Value *Ptr = Dbg->getAddress()) {
                            VarMap[Ptr] = Var->getName().str();
                        }
                    }
                }
            }
        }
    }

    bool runOnModule(Module &M) override {
        LLVMContext &Ctx = M.getContext();

        // int printf(const char*, ...)
        Constant *PrintF = M.getOrInsertFunction(
            "printf",
            FunctionType::get(IntegerType::getInt32Ty(Ctx),
                              PointerType::get(Type::getInt8Ty(Ctx), 0),
                              /*isVarArg=*/true));

        bool Modified = false;

        for (Function &F : M) {
            if (F.isDeclaration()) continue;

            VarMap.clear();
            buildVarMap(F);

            for (BasicBlock &BB : F) {
                for (Instruction &I : BB) {
                    if (auto *Store = dyn_cast<StoreInst>(&I)) {
                        IRBuilder<> B(Store->getNextNode());

                        Value *StoredVal = Store->getValueOperand();
                        Value *Ptr       = Store->getPointerOperand();

                        std::string VarName = "<unknown>";
                        if (VarMap.count(Ptr)) {
                            VarName = VarMap[Ptr];
                        } else if (Ptr->hasName()) {
                            VarName = Ptr->getName().str();
                        }

                        std::string FilePath = getFileFromInst(*Store);
                        if (FilePath == "<nofile>") {
                            FilePath = getFileFromFunction(F);
                        }

                        if (StoredVal->getType()->isIntegerTy()) {
                            // ("func", "var", 123, "/path/to/file.c")
                            std::string Msg = "(\"" + F.getName().str() +
                                              "\", \"" + VarName +
                                              "\", %lld, \"" + FilePath + "\")\n";

                            Value *Fmt = B.CreateGlobalStringPtr(Msg);
                            Value *Arg = toI64(B, StoredVal, /*signExtend=*/true);
                            B.CreateCall(PrintF, {Fmt, Arg});
                            Modified = true;
                        }
                    }
                }
            }
        }

        return Modified;
    }
};

} // anonymous namespace

char VarTracerPass::ID = 0;
static RegisterPass<VarTracerPass> X(
    "var-trace",
    "Variable Tracing Pass (tuple-friendly output with file path only)",
    false, // Only looks at CFG?
    false  // Analysis Pass?
);
